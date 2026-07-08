# =============================================================================
#  ALL-IN-ONE DISCORD BOT  (discord.py 2.x)  —  single-file build
# =============================================================================
#  Features bundled in this one script:
#    * Welcome        – greets new members + optional auto-role
#    * Rules          – posts rules with an "Accept" button that grants a role
#    * Announcements  – staff command that opens a modal and posts an embed
#    * Tickets        – button panel -> private channels + transcript on close
#    * Sanction logs  – warn / kick / ban / timeout, stored + logged + history
#    * Voice panel    – "join to create" temp voice channels + control buttons
#
#  ---------------------------------------------------------------------------
#  SETUP
#  1) python -m pip install -U "discord.py>=2.3"
#  2) Fill in the CONFIG block below (channel & role IDs — right-click in
#     Discord with Developer Mode on -> "Copy ID").
#  3) Set environment variables (or hardcode them in CONFIG):
#        DISCORD_TOKEN = your bot token
#        CLIENT_ID     = your application (bot) ID   (optional here)
#        GUILD_ID      = your server ID
#  4) In the Developer Portal -> Bot, enable the PRIVILEGED INTENTS:
#        - SERVER MEMBERS INTENT      (required for the welcome feature)
#        - MESSAGE CONTENT INTENT     (optional — only for full ticket
#                                      transcript text; toggle it below)
#  5) Invite the bot with the "bot" + "applications.commands" scopes and the
#     Administrator permission (or at least Manage Channels/Roles, Kick, Ban,
#     Moderate Members, Move Members, Manage Messages).
#  6) python main.py
#
#  Persistence: a local `data.json` file next to this script stores sanctions
#  and the ticket counter. No external database required.
# =============================================================================

import os
import re
import json
import asyncio
from datetime import datetime, timedelta, timezone

import discord
from discord import app_commands
from discord.ext import commands

# ============================== CONFIG =======================================
CONFIG = {
    "token":     os.getenv("DISCORD_TOKEN", "YOUR_BOT_TOKEN"),
    "client_id": os.getenv("CLIENT_ID",     "YOUR_CLIENT_ID"),
    "guild_id":  os.getenv("GUILD_ID",      "YOUR_GUILD_ID"),

    "channels": {
        "welcome":         "000000000000000000",  # where welcome messages are sent
        "rules":           "000000000000000000",  # where /rules posts the panel
        "announcements":   "000000000000000000",  # where /announce posts
        "mod_log":         "000000000000000000",  # sanction log channel
        "ticket_category": "000000000000000000",  # category new tickets go in
        "ticket_log":      "000000000000000000",  # where transcripts are logged
        "join_to_create":  "000000000000000000",  # join this VC to spawn a temp VC
        "temp_vc_category": "000000000000000000",  # category temp VCs are created in
    },

    "roles": {
        "member": "000000000000000000",  # granted when a user accepts the rules
        "staff":  "000000000000000000",  # may use moderation & manage tickets
    },

    "colors": {
        "primary": 0x5865F2,
        "success": 0x57F287,
        "warning": 0xFEE75C,
        "danger":  0xED4245,
        "voice":   0x9B59B6,
    },
}

# Set True only if you enabled the MESSAGE CONTENT privileged intent and want
# full message text inside ticket transcripts.
USE_MESSAGE_CONTENT = False
# =============================================================================


# ------------------------- tiny JSON storage ---------------------------------
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")


def load_data() -> dict:
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"sanctions": {}, "ticket_counter": 0}


def save_data(data: dict) -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError as exc:
        print(f"Failed to save data.json: {exc}")


db = load_data()

# in-memory map of temp voice channels:  channel_id -> owner_id
temp_channels: dict[int, int] = {}


# --------------------------- helpers -----------------------------------------
def color(name: str) -> discord.Color:
    return discord.Color(CONFIG["colors"][name])


def is_placeholder(cid) -> bool:
    s = str(cid)
    return not s or bool(re.fullmatch(r"0+", s)) or s.startswith("YOUR_")


def get_channel(guild: discord.Guild, cid):
    if is_placeholder(cid):
        return None
    return guild.get_channel(int(cid))


def role_id(name: str):
    val = CONFIG["roles"][name]
    return None if is_placeholder(val) else int(val)


def is_staff(member: discord.Member) -> bool:
    if member is None:
        return False
    rid = role_id("staff")
    if rid and any(r.id == rid for r in member.roles):
        return True
    return member.guild_permissions.moderate_members


def parse_duration(text: str):
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", str(text), re.IGNORECASE)
    if not m:
        return None
    n = int(m.group(1))
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2).lower()]
    return timedelta(seconds=n * mult)


def add_sanction(user_id: int, entry: dict) -> None:
    key = str(user_id)
    db["sanctions"].setdefault(key, []).append(entry)
    save_data(db)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def log_to_mod_channel(guild: discord.Guild, embed: discord.Embed) -> None:
    ch = get_channel(guild, CONFIG["channels"]["mod_log"])
    if ch:
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass


# discord.py has no built-in .kickable / .bannable, so we mirror the checks.
def can_manage(guild: discord.Guild, target: discord.Member) -> bool:
    if target == guild.owner:
        return False
    me = guild.me
    return me.top_role > target.top_role


# --------------------------- client ------------------------------------------
intents = discord.Intents.default()
intents.members = True         # privileged – for welcome
intents.voice_states = True    # for temp voice channels
if USE_MESSAGE_CONTENT:
    intents.message_content = True  # privileged – full transcript text


class AllInOneBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!unused!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        # register persistent views so buttons survive restarts
        self.add_view(RulesView())
        self.add_view(TicketPanelView())
        self.add_view(TicketControlView())
        self.add_view(VoicePanelView())

        # -------- slash command sync --------
        # If GUILD_ID is set: sync to that guild (appears INSTANTLY).
        # If not: fall back to a GLOBAL sync so commands still register
        #         (global can take up to ~1 hour to show up in Discord).
        try:
            if not is_placeholder(CONFIG["guild_id"]):
                guild = discord.Object(id=int(CONFIG["guild_id"]))
                self.tree.copy_global_to(guild=guild)
                synced = await self.tree.sync(guild=guild)
                print(f"\u2714 Registered {len(synced)} slash commands to guild "
                      f"{CONFIG['guild_id']} (instant).")
            else:
                synced = await self.tree.sync()
                print(f"\u2714 Registered {len(synced)} GLOBAL slash commands "
                      f"(GUILD_ID not set — may take up to 1 hour to appear).")
            print("   Commands:", ", ".join(sorted(c.name for c in synced)))
        except discord.Forbidden:
            print("\u274c Sync FAILED (Forbidden). The bot was likely invited WITHOUT the "
                  "'applications.commands' scope. Re-invite it with both 'bot' and "
                  "'applications.commands' scopes.")
        except Exception as exc:  # noqa: BLE001 - surface any sync error in logs
            print(f"\u274c Slash command sync failed: {type(exc).__name__}: {exc}")


bot = AllInOneBot()
tree = bot.tree


@bot.event
async def on_ready():
    print("=" * 60)
    print(f"\u2714 Logged in as {bot.user} ({bot.user.id})")
    print(f"  Connected to {len(bot.guilds)} guild(s): "
          f"{', '.join(g.name for g in bot.guilds) or '(none)'}")
    if is_placeholder(CONFIG['guild_id']):
        print("  \u26a0 GUILD_ID is not set — using GLOBAL commands (slow to appear).")
        print("    Set GUILD_ID to your server ID for INSTANT command registration.")
    print("  Type '/' in Discord and pick a command from the popup (not '.rules').")
    print("=" * 60)
    await bot.change_presence(
        activity=discord.Activity(type=discord.ActivityType.watching, name="over the server")
    )


# =========================== WELCOME =========================================
@bot.event
async def on_member_join(member: discord.Member):
    ch = get_channel(member.guild, CONFIG["channels"]["welcome"])
    if not ch:
        return

    embed = discord.Embed(
        color=color("success"),
        title="\U0001F44B Welcome!",
        description=(
            f"Welcome to **{member.guild.name}**, {member.mention}!\n"
            f"You are member **#{member.guild.member_count}**.\n"
            f"Head to the rules channel to unlock the rest of the server."
        ),
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.timestamp = discord.utils.utcnow()

    try:
        await ch.send(content=member.mention, embed=embed)
    except discord.HTTPException:
        pass

    # optional auto-role on join could be added here if desired.


# =========================== RULES ===========================================
class RulesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="J'accepte les règles", style=discord.ButtonStyle.success,
        emoji="\u2705", custom_id="rules_accept",
    )
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        rid = role_id("member")
        if rid is None:
            return await interaction.response.send_message(
                "\u2705 Merci d'avoir accepté les règles !", ephemeral=True)

        role = interaction.guild.get_role(rid)
        if role is None:
            return await interaction.response.send_message(
                "\u26a0\ufe0f Rôle Membre introuvable — contactez le staff.", ephemeral=True)

        if role in interaction.user.roles:
            return await interaction.response.send_message(
                "\u2139\ufe0f Vous avez déjà accès.", ephemeral=True)

        await interaction.user.add_roles(role, reason="A accepté les règles")
        await interaction.response.send_message(
            f"\u2705 Merci ! Le rôle **{role.name}** vous a été attribué.", ephemeral=True)


@tree.command(name="rules", description="Poster le panneau des règles (staff)")
@app_commands.default_permissions(manage_guild=True)
async def cmd_rules(interaction: discord.Interaction):
    embed = discord.Embed(
        color=color("primary"),
        title="\U0001F4DC Règles du serveur",
        description="\n".join([
            "**1. Respect :** Traitez tous les membres et le personnel avec respect. "
            "Maintenez un environnement amical, mature et approprié.",
            "**2. Pas de discours de haine :** Le racisme, le sexisme, l'homophobie ou tout "
            "contenu dégradant sont strictement interdits. Soutenir ou adopter un tel "
            "comportement entraînera un bannissement.",
            "**3. Blagues appropriées :** Les blagues inappropriées sont strictement interdites.",
            "**4. Pas de NSFW :** Le contenu ou les discussions NSFW (y compris tout matériel "
            "similaire) ne sont pas autorisés.",
            "**5. Pas de publicité :** La publicité sur ce serveur est interdite.",
            "**6. Vie privée :** Ne demandez pas, ne partagez pas et ne divulguez pas "
            "d'informations personnelles. Cela est strictement interdit.",
            "**7. Utilisation des salons :** Utilisez les salons uniquement pour l'usage auquel "
            "ils sont destinés. Le spam ou la mauvaise utilisation des salons est interdit.",
            "**8. Pseudos :** Ne gardez pas de pseudos ou surnoms inappropriés ; ils seront "
            "modérés.",
            "**9. Filtres :** Tenter de contourner les filtres de mots ou le système "
            "d'auto-modération du serveur est interdit.",
            "**10. Pas de menaces :** Les menaces de toute nature envers les membres ou "
            "quiconque ne seront pas tolérées.",
            "**11. Pas de contournement des règles :** N'essayez pas de contourner les règles "
            "du serveur.",
            "**12. Pas de mendicité :** Demander de manière insistante des objets gratuits tels "
            "que des boosts, des gamepasses ou des produits n'est pas autorisé.",
            "",
            "Profitez bien du serveur ! Veuillez respecter les règles :",
            "\u2022 Discord Terms : https://discord.com/terms",
            "\u2022 Discord Guidelines : https://discord.com/guidelines",
            "\u2022 Roblox Terms : https://en.help.roblox.com/hc/en-us/articles/"
            "115004647846-Roblox-Terms-of-Use",
            "",
            "Cliquez sur le bouton ci-dessous pour confirmer que vous avez lu et accepté "
            "les règles.",
        ]),
    )
    embed.set_footer(text="Enfreindre les règles peut entraîner des sanctions.")

    target = get_channel(interaction.guild, CONFIG["channels"]["rules"]) or interaction.channel
    await target.send(embed=embed, view=RulesView())
    await interaction.response.send_message(
        f"\u2705 Règles postées dans {target.mention}.", ephemeral=True)


# =========================== ANNOUNCEMENTS ===================================
class AnnounceModal(discord.ui.Modal, title="New Announcement"):
    a_title = discord.ui.TextInput(
        label="Title", style=discord.TextStyle.short, required=True, max_length=256)
    a_body = discord.ui.TextInput(
        label="Message", style=discord.TextStyle.paragraph, required=True, max_length=3800)
    a_ping = discord.ui.TextInput(
        label="Ping? (everyone / here / none)", style=discord.TextStyle.short,
        required=False, placeholder="none")

    async def on_submit(self, interaction: discord.Interaction):
        ping = (self.a_ping.value or "").lower().strip()
        content = ""
        allowed = discord.AllowedMentions.none()
        if ping == "everyone":
            content = "@everyone"
            allowed = discord.AllowedMentions(everyone=True)
        elif ping == "here":
            content = "@here"
            allowed = discord.AllowedMentions(everyone=True)

        embed = discord.Embed(
            color=color("primary"),
            title=f"\U0001F4E2 {self.a_title.value}",
            description=self.a_body.value,
        )
        embed.set_footer(text=f"Announced by {interaction.user}")
        embed.timestamp = discord.utils.utcnow()

        ch = get_channel(interaction.guild, CONFIG["channels"]["announcements"]) or interaction.channel
        await ch.send(content=content, embed=embed, allowed_mentions=allowed)
        await interaction.response.send_message(
            f"\u2705 Announcement posted in {ch.mention}.", ephemeral=True)


@tree.command(name="announce", description="Open the announcement composer (staff)")
@app_commands.default_permissions(manage_guild=True)
async def cmd_announce(interaction: discord.Interaction):
    await interaction.response.send_modal(AnnounceModal())


# =========================== TICKETS =========================================
class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open a ticket", style=discord.ButtonStyle.primary,
        emoji="\U0001F3AB", custom_id="ticket_open",
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild

        # prevent duplicate open tickets (identified via channel topic)
        existing = discord.utils.find(
            lambda c: isinstance(c, discord.TextChannel)
            and c.topic == f"ticket-owner:{interaction.user.id}",
            guild.channels,
        )
        if existing:
            return await interaction.followup.send(
                f"\u2757 You already have an open ticket: {existing.mention}", ephemeral=True)

        db["ticket_counter"] = db.get("ticket_counter", 0) + 1
        save_data(db)
        num = str(db["ticket_counter"]).zfill(4)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True,
                read_message_history=True, attach_files=True),
        }
        staff_rid = role_id("staff")
        staff_role = guild.get_role(staff_rid) if staff_rid else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True)

        cat_id = CONFIG["channels"]["ticket_category"]
        category = None if is_placeholder(cat_id) else guild.get_channel(int(cat_id))

        channel = await guild.create_text_channel(
            name=f"ticket-{num}",
            category=category,
            topic=f"ticket-owner:{interaction.user.id}",
            overwrites=overwrites,
        )

        embed = discord.Embed(
            color=color("primary"),
            title=f"\U0001F3AB Ticket #{num}",
            description=(
                f"Hello {interaction.user.mention}, thanks for reaching out.\n"
                f"Describe your issue and a staff member will be with you shortly."
            ),
        )
        staff_mention = f"<@&{staff_rid}>" if staff_rid else ""
        content = f"{interaction.user.mention} {staff_mention}".strip()
        await channel.send(content=content, embed=embed, view=TicketControlView())

        await interaction.followup.send(
            f"\u2705 Your ticket has been created: {channel.mention}", ephemeral=True)


class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Claim", style=discord.ButtonStyle.secondary,
        emoji="\U0001F64B", custom_id="ticket_claim",
    )
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_staff(interaction.user):
            return await interaction.response.send_message(
                "\u274c Only staff can claim tickets.", ephemeral=True)
        await interaction.response.send_message(
            f"\U0001F64B {interaction.user.mention} has claimed this ticket.")

    @discord.ui.button(
        label="Close", style=discord.ButtonStyle.danger,
        emoji="\U0001F512", custom_id="ticket_close",
    )
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=60)
        view.add_item(_TicketCloseConfirmButton())
        await interaction.response.send_message(
            "Are you sure you want to close this ticket?", view=view, ephemeral=True)


class _TicketCloseConfirmButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Confirm close", style=discord.ButtonStyle.danger, emoji="\u26d4")

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        await interaction.response.edit_message(content="\U0001F512 Closing ticket\u2026", view=None)

        # build a text transcript (full text needs MESSAGE CONTENT intent)
        lines = [
            f"Transcript for #{channel.name}",
            f"Closed by {interaction.user} at {now_iso()}",
            "",
        ]
        try:
            msgs = [m async for m in channel.history(limit=100, oldest_first=True)]
            for m in msgs:
                body = m.content if (USE_MESSAGE_CONTENT and m.content) else "[embed / attachment]"
                lines.append(f"[{m.created_at.isoformat()}] {m.author}: {body}")
        except discord.HTTPException:
            pass
        transcript = "\n".join(lines)

        log_ch = get_channel(interaction.guild, CONFIG["channels"]["ticket_log"])
        if log_ch:
            file = discord.File(
                fp=_bytes_io(transcript), filename=f"{channel.name}.txt")
            embed = discord.Embed(color=color("danger"), title="\U0001F3AB Ticket closed")
            embed.add_field(name="Ticket", value=channel.name, inline=True)
            embed.add_field(name="Closed by", value=interaction.user.mention, inline=True)
            embed.timestamp = discord.utils.utcnow()
            try:
                await log_ch.send(embed=embed, file=file)
            except discord.HTTPException:
                pass

        await asyncio.sleep(4)
        try:
            await channel.delete()
        except discord.HTTPException:
            pass


def _bytes_io(text: str):
    import io
    return io.BytesIO(text.encode("utf-8"))


@tree.command(name="ticket-panel", description="Post the ticket creation panel (staff)")
@app_commands.default_permissions(manage_guild=True)
async def cmd_ticket_panel(interaction: discord.Interaction):
    embed = discord.Embed(
        color=color("primary"),
        title="\U0001F3AB Support Tickets",
        description=(
            "Need help or want to contact the staff team?\n"
            "Click the button below to open a private ticket."
        ),
    )
    await interaction.channel.send(embed=embed, view=TicketPanelView())
    await interaction.response.send_message("\u2705 Ticket panel posted.", ephemeral=True)


# =========================== SANCTIONS =======================================
@tree.command(name="warn", description="Warn a member")
@app_commands.describe(user="Member to warn", reason="Reason")
@app_commands.default_permissions(moderate_members=True)
async def cmd_warn(interaction: discord.Interaction, user: discord.User, reason: str):
    add_sanction(user.id, {
        "type": "warn", "reason": reason,
        "moderator": interaction.user.id, "date": now_iso()})

    embed = discord.Embed(color=color("warning"), title="\u26a0\ufe0f Warning issued")
    embed.add_field(name="Member", value=f"{user.mention} ({user})", inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()

    await log_to_mod_channel(interaction.guild, embed)
    try:
        await user.send(
            f"You have been **warned** in **{interaction.guild.name}**.\nReason: {reason}")
    except discord.HTTPException:
        pass
    await interaction.response.send_message(f"\u26a0\ufe0f Warned {user}.", ephemeral=True)


@tree.command(name="timeout", description="Timeout (mute) a member")
@app_commands.describe(user="Member", duration="e.g. 10m, 1h, 1d (max 28d)", reason="Reason")
@app_commands.default_permissions(moderate_members=True)
async def cmd_timeout(interaction: discord.Interaction, user: discord.Member,
                      duration: str, reason: str = "No reason provided"):
    delta = parse_duration(duration)
    if delta is None:
        return await interaction.response.send_message(
            "\u274c Invalid duration. Use e.g. `10m`, `1h`, `1d`.", ephemeral=True)
    capped = min(delta, timedelta(days=28))

    if not can_manage(interaction.guild, user):
        return await interaction.response.send_message(
            "\u274c I can't timeout this member (role hierarchy).", ephemeral=True)

    await user.timeout(capped, reason=reason)
    add_sanction(user.id, {
        "type": "timeout", "reason": reason, "moderator": interaction.user.id,
        "date": now_iso(), "extra": duration})

    embed = discord.Embed(color=color("warning"), title="\U0001F507 Member timed out")
    embed.add_field(name="Member", value=f"{user.mention} ({user})", inline=True)
    embed.add_field(name="Duration", value=duration, inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await log_to_mod_channel(interaction.guild, embed)
    await interaction.response.send_message(
        f"\U0001F507 Timed out {user} for {duration}.", ephemeral=True)


@tree.command(name="untimeout", description="Remove a timeout")
@app_commands.describe(user="Member")
@app_commands.default_permissions(moderate_members=True)
async def cmd_untimeout(interaction: discord.Interaction, user: discord.Member):
    await user.timeout(None, reason=f"Timeout removed by {interaction.user}")
    await interaction.response.send_message(
        f"\U0001F50A Timeout removed for {user}.", ephemeral=True)


@tree.command(name="kick", description="Kick a member")
@app_commands.describe(user="Member", reason="Reason")
@app_commands.default_permissions(kick_members=True)
async def cmd_kick(interaction: discord.Interaction, user: discord.Member,
                   reason: str = "No reason provided"):
    if not can_manage(interaction.guild, user):
        return await interaction.response.send_message(
            "\u274c I can't kick this member (role hierarchy).", ephemeral=True)

    try:
        await user.send(
            f"You have been **kicked** from **{interaction.guild.name}**.\nReason: {reason}")
    except discord.HTTPException:
        pass
    await user.kick(reason=reason)
    add_sanction(user.id, {
        "type": "kick", "reason": reason,
        "moderator": interaction.user.id, "date": now_iso()})

    embed = discord.Embed(color=color("danger"), title="\U0001F462 Member kicked")
    embed.add_field(name="Member", value=f"{user} ({user.id})", inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await log_to_mod_channel(interaction.guild, embed)
    await interaction.response.send_message(f"\U0001F462 Kicked {user}.", ephemeral=True)


@tree.command(name="ban", description="Ban a member")
@app_commands.describe(
    user="Member", reason="Reason", delete_days="Delete last N days of messages (0-7)")
@app_commands.default_permissions(ban_members=True)
async def cmd_ban(interaction: discord.Interaction, user: discord.User,
                  reason: str = "No reason provided", delete_days: int = 0):
    delete_days = max(0, min(7, delete_days))
    member = interaction.guild.get_member(user.id)
    if member and not can_manage(interaction.guild, member):
        return await interaction.response.send_message(
            "\u274c I can't ban this member (role hierarchy).", ephemeral=True)

    try:
        await user.send(
            f"You have been **banned** from **{interaction.guild.name}**.\nReason: {reason}")
    except discord.HTTPException:
        pass
    await interaction.guild.ban(
        user, reason=reason, delete_message_seconds=delete_days * 86400)
    add_sanction(user.id, {
        "type": "ban", "reason": reason,
        "moderator": interaction.user.id, "date": now_iso()})

    embed = discord.Embed(color=color("danger"), title="\U0001F528 Member banned")
    embed.add_field(name="Member", value=f"{user} ({user.id})", inline=True)
    embed.add_field(name="Moderator", value=interaction.user.mention, inline=True)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.timestamp = discord.utils.utcnow()
    await log_to_mod_channel(interaction.guild, embed)
    await interaction.response.send_message(f"\U0001F528 Banned {user}.", ephemeral=True)


@tree.command(name="unban", description="Unban a user by ID")
@app_commands.describe(user_id="User ID")
@app_commands.default_permissions(ban_members=True)
async def cmd_unban(interaction: discord.Interaction, user_id: str):
    try:
        await interaction.guild.unban(discord.Object(id=int(user_id)))
        await interaction.response.send_message(f"\u2705 Unbanned <@{user_id}>.", ephemeral=True)
    except (discord.HTTPException, ValueError):
        await interaction.response.send_message(
            "\u274c Could not unban (not banned or invalid ID).", ephemeral=True)


@tree.command(name="sanctions", description="View a member's sanction history")
@app_commands.describe(user="Member")
@app_commands.default_permissions(moderate_members=True)
async def cmd_sanctions(interaction: discord.Interaction, user: discord.User):
    records = db["sanctions"].get(str(user.id), [])
    if not records:
        return await interaction.response.send_message(
            f"\u2705 {user} has no sanctions on record.", ephemeral=True)

    icons = {"warn": "\u26a0\ufe0f", "kick": "\U0001F462",
             "ban": "\U0001F528", "timeout": "\U0001F507"}
    lines = []
    for i, s in enumerate(records[-25:], start=1):
        ts = int(datetime.fromisoformat(s["date"]).timestamp())
        extra = f" ({s['extra']})" if s.get("extra") else ""
        lines.append(
            f"**{i}.** {icons.get(s['type'], '\u2022')} `{s['type']}`{extra} — {s['reason']}\n"
            f"\u2517 by <@{s['moderator']}> <t:{ts}:R>")

    embed = discord.Embed(
        color=color("warning"),
        title=f"\U0001F4C1 Sanctions — {user}",
        description="\n\n".join(lines),
    )
    embed.set_footer(text=f"{len(records)} total record(s)")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="clear", description="Supprimer un nombre de messages dans ce salon")
@app_commands.describe(amount="Nombre de messages à supprimer (1-100)",
                       user="Optionnel : ne supprimer que les messages de ce membre")
@app_commands.default_permissions(manage_messages=True)
async def cmd_clear(interaction: discord.Interaction, amount: int,
                    user: discord.User = None):
    if amount < 1 or amount > 100:
        return await interaction.response.send_message(
            "\u274c Choisissez un nombre entre 1 et 100.", ephemeral=True)

    # channels must be text-capable for bulk delete
    if not isinstance(interaction.channel, (discord.TextChannel, discord.Thread,
                                            discord.VoiceChannel)):
        return await interaction.response.send_message(
            "\u274c Impossible de supprimer des messages ici.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)

    def check(m: discord.Message) -> bool:
        return user is None or m.author.id == user.id

    try:
        # bulk_delete only works on messages younger than 14 days
        deleted = await interaction.channel.purge(limit=amount, check=check)
    except discord.Forbidden:
        return await interaction.followup.send(
            "\u274c Il me manque la permission **Gérer les messages**.", ephemeral=True)
    except discord.HTTPException as exc:
        return await interaction.followup.send(
            f"\u274c Échec de la suppression : {exc}", ephemeral=True)

    who = f" de {user.mention}" if user else ""
    await interaction.followup.send(
        f"\U0001F9F9 {len(deleted)} message(s){who} supprimé(s).", ephemeral=True)

    # log it if a mod-log channel is configured
    log_embed = discord.Embed(color=color("warning"), title="\U0001F9F9 Messages supprimés")
    log_embed.add_field(name="Salon", value=interaction.channel.mention, inline=True)
    log_embed.add_field(name="Quantité", value=str(len(deleted)), inline=True)
    log_embed.add_field(name="Modérateur", value=interaction.user.mention, inline=True)
    if user:
        log_embed.add_field(name="Cible", value=f"{user} ({user.id})", inline=False)
    log_embed.timestamp = discord.utils.utcnow()
    await log_to_mod_channel(interaction.guild, log_embed)


@tree.command(name="clear-sanctions", description="Clear a member's sanctions (admin)")
@app_commands.describe(user="Member")
@app_commands.default_permissions(administrator=True)
async def cmd_clear_sanctions(interaction: discord.Interaction, user: discord.User):
    count = len(db["sanctions"].get(str(user.id), []))
    db["sanctions"].pop(str(user.id), None)
    save_data(db)
    await interaction.response.send_message(
        f"\U0001F9F9 Cleared {count} sanction(s) for {user}.", ephemeral=True)


# =========================== VOICE PANEL =====================================
@bot.event
async def on_voice_state_update(member: discord.Member,
                                before: discord.VoiceState, after: discord.VoiceState):
    j2c = CONFIG["channels"]["join_to_create"]

    # "Join to create" -> spawn a personal temp voice channel
    if (after.channel and not is_placeholder(j2c)
            and after.channel.id == int(j2c)):
        guild = member.guild
        try:
            cat_id = CONFIG["channels"]["temp_vc_category"]
            if is_placeholder(cat_id):
                category = after.channel.category
            else:
                category = guild.get_channel(int(cat_id))

            overwrites = {
                member: discord.PermissionOverwrite(
                    manage_channels=True, move_members=True),
            }
            vc = await guild.create_voice_channel(
                name=f"{member.display_name}'s channel",
                category=category,
                overwrites=overwrites,
            )
            temp_channels[vc.id] = member.id
            try:
                await member.move_to(vc)
            except discord.HTTPException:
                pass
            await send_voice_panel(vc)
        except discord.HTTPException as exc:
            print(f"Failed to create temp VC: {exc}")

    # Clean up temp channels once everyone leaves
    if before.channel and before.channel.id in temp_channels:
        ch = before.channel
        if len(ch.members) == 0:
            temp_channels.pop(ch.id, None)
            try:
                await ch.delete()
            except discord.HTTPException:
                pass


class VoicePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def _guard(self, interaction: discord.Interaction):
        """Return owner_id if the panel is valid, else None (and reply)."""
        owner_id = temp_channels.get(interaction.channel.id)
        if owner_id is None:
            await interaction.response.send_message(
                "\u274c This panel is not linked to a temporary voice channel.", ephemeral=True)
            return None
        return owner_id

    def _is_owner(self, interaction, owner_id) -> bool:
        return interaction.user.id == owner_id or is_staff(interaction.user)

    @discord.ui.button(emoji="\U0001F512", style=discord.ButtonStyle.secondary, custom_id="vc_lock", row=0)
    async def lock(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.channel.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message("\U0001F512 Channel locked.", ephemeral=True)

    @discord.ui.button(emoji="\U0001F513", style=discord.ButtonStyle.secondary, custom_id="vc_unlock", row=0)
    async def unlock(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.channel.set_permissions(interaction.guild.default_role, connect=None)
        await interaction.response.send_message("\U0001F513 Channel unlocked.", ephemeral=True)

    @discord.ui.button(emoji="\U0001F648", style=discord.ButtonStyle.secondary, custom_id="vc_hide", row=0)
    async def hide(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message("\U0001F648 Channel hidden.", ephemeral=True)

    @discord.ui.button(emoji="\U0001F440", style=discord.ButtonStyle.secondary, custom_id="vc_unhide", row=0)
    async def unhide(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.channel.set_permissions(interaction.guild.default_role, view_channel=None)
        await interaction.response.send_message("\U0001F440 Channel visible.", ephemeral=True)

    @discord.ui.button(emoji="\U0001F451", style=discord.ButtonStyle.success, custom_id="vc_claim", row=0)
    async def claim(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if any(m.id == owner_id for m in interaction.channel.members):
            return await interaction.response.send_message(
                "\u274c The current owner is still in the channel.", ephemeral=True)
        temp_channels[interaction.channel.id] = interaction.user.id
        await interaction.response.send_message(
            f"\U0001F451 {interaction.user.mention} is now the owner of this channel.")

    @discord.ui.button(emoji="\U0001F522", style=discord.ButtonStyle.primary, custom_id="vc_limit", row=1)
    async def limit(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.response.send_modal(VcLimitModal())

    @discord.ui.button(emoji="\u270F\ufe0f", style=discord.ButtonStyle.primary, custom_id="vc_rename", row=1)
    async def rename(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.response.send_modal(VcRenameModal())

    @discord.ui.button(emoji="\U0001F462", style=discord.ButtonStyle.danger, custom_id="vc_kick", row=1)
    async def kick(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        view = discord.ui.View(timeout=60)
        view.add_item(_VcKickSelect())
        await interaction.response.send_message(
            "Who do you want to disconnect?", view=view, ephemeral=True)

    @discord.ui.button(emoji="\U0001F5D1\ufe0f", style=discord.ButtonStyle.danger, custom_id="vc_delete", row=1)
    async def delete(self, interaction, button):
        owner_id = await self._guard(interaction)
        if owner_id is None:
            return
        if not self._is_owner(interaction, owner_id):
            return await _deny_owner(interaction)
        await interaction.response.send_message("\U0001F5D1\ufe0f Deleting channel\u2026", ephemeral=True)
        temp_channels.pop(interaction.channel.id, None)
        try:
            await interaction.channel.delete()
        except discord.HTTPException:
            pass


async def _deny_owner(interaction: discord.Interaction):
    await interaction.response.send_message(
        "\u274c Only the channel owner can do that.", ephemeral=True)


class VcLimitModal(discord.ui.Modal, title="Set user limit"):
    value = discord.ui.TextInput(
        label="User limit (0 = unlimited, max 99)", style=discord.TextStyle.short, required=True)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.value.value)
        except ValueError:
            val = -1
        if val < 0 or val > 99:
            return await interaction.response.send_message(
                "\u274c Enter a number between 0 and 99.", ephemeral=True)
        await interaction.channel.edit(user_limit=val)
        await interaction.response.send_message(
            f"\U0001F522 User limit set to {'unlimited' if val == 0 else val}.", ephemeral=True)


class VcRenameModal(discord.ui.Modal, title="Rename channel"):
    value = discord.ui.TextInput(
        label="New name", style=discord.TextStyle.short, required=True, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        name = self.value.value[:100]
        await interaction.channel.edit(name=name)
        await interaction.response.send_message(
            f"\u270F\ufe0f Renamed to **{name}**.", ephemeral=True)


class _VcKickSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Select a member to disconnect", min_values=1, max_values=1)

    async def callback(self, interaction: discord.Interaction):
        channel = interaction.channel
        owner_id = temp_channels.get(channel.id)
        if owner_id is None:
            return await interaction.response.edit_message(
                content="\u274c Channel no longer exists.", view=None)
        if interaction.user.id != owner_id and not is_staff(interaction.user):
            return await interaction.response.edit_message(
                content="\u274c Only the owner can do that.", view=None)

        target = self.values[0]
        member = interaction.guild.get_member(target.id)
        if not member or not member.voice or member.voice.channel != channel:
            return await interaction.response.edit_message(
                content="\u274c That member is not in this channel.", view=None)
        try:
            await member.move_to(None)
        except discord.HTTPException:
            pass
        await interaction.response.edit_message(
            content=f"\U0001F462 Disconnected {member}.", view=None)


async def send_voice_panel(channel: discord.VoiceChannel):
    owner_id = temp_channels.get(channel.id)
    embed = discord.Embed(
        color=color("voice"),
        title="\U0001F399\ufe0f Voice Control Panel",
        description=(
            f"Owner: <@{owner_id}>\n"
            f"Use the buttons below to manage your channel."
        ),
    )
    embed.add_field(name="\U0001F512 / \U0001F513", value="Lock / Unlock", inline=True)
    embed.add_field(name="\U0001F648 / \U0001F440", value="Hide / Unhide", inline=True)
    embed.add_field(name="\U0001F451", value="Claim ownership", inline=True)
    embed.add_field(name="\U0001F522 / \u270F\ufe0f", value="User limit / Rename", inline=True)
    embed.add_field(name="\U0001F462 / \U0001F5D1\ufe0f", value="Kick / Delete", inline=True)
    try:
        await channel.send(embed=embed, view=VoicePanelView())
    except discord.HTTPException:
        pass


@tree.command(name="voice-panel", description="Repost the voice control panel in your temp VC")
async def cmd_voice_panel(interaction: discord.Interaction):
    vc = interaction.user.voice.channel if interaction.user.voice else None
    if not vc or vc.id not in temp_channels:
        return await interaction.response.send_message(
            "\u274c You must be in your own temporary voice channel.", ephemeral=True)
    await send_voice_panel(vc)
    await interaction.response.send_message("\u2705 Panel reposted.", ephemeral=True)


# --------------------------- error handling ----------------------------------
@tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    print(f"App command error: {error}")
    msg = "\u26a0\ufe0f Something went wrong."
    if isinstance(error, app_commands.MissingPermissions):
        msg = "\u274c You don't have permission to use that."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except discord.HTTPException:
        pass


# --------------------------- boot --------------------------------------------
if __name__ == "__main__":
    if is_placeholder(CONFIG["token"]):
        raise SystemExit("Set DISCORD_TOKEN (env var) or hardcode it in CONFIG['token'].")
    bot.run(CONFIG["token"])
