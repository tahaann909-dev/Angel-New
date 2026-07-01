import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import random
import asyncio
import datetime
import time
import re
import hashlib
import base64
import binascii
import codecs
import zlib
import uuid
import secrets
import socket
import string as _string
import math as _math
import urllib.parse
import aiohttp
from collections import defaultdict, Counter

load_dotenv()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=".", intents=intents, help_command=None)

# ── STORAGE ────────────────────────────────────────────────────────────────────
warn_data         = defaultdict(list)
mute_data         = {}
snipe_data        = {}
edit_snipe_data   = {}
afk_data          = {}
economy_data      = defaultdict(lambda: 500)
bank_data         = defaultdict(int)
xp_data           = defaultdict(int)
level_data        = defaultdict(int)
notes_data        = defaultdict(list)
todo_data         = defaultdict(list)
reminder_data     = []
blacklisted_words = set()
join_logs         = {}
autorole_data     = {}
giveaway_data     = {}
daily_cd          = {}
work_cd           = {}
rob_cd            = {}
weekly_cd         = {}
hourly_cd         = {}
crime_cd          = {}
dig_cd            = {}
fish_cd           = {}
quest_cd          = {}
interest_cd       = {}
trivia_answers    = {}
spam_tracker      = defaultdict(list)
reaction_roles    = {}
sticky_messages   = {}
tag_data          = {}
birthday_data     = {}
confession_ch     = {}
suggestion_ch     = {}
starboard_data    = {}
starboard_posted  = set()
counting_data     = {}
log_channel_data  = {}
welcome_data      = {}
goodbye_data      = {}
inventory_data    = defaultdict(list)
lottery_entries   = []
lottery_pot       = 0
locked_channels   = set()
level_roles       = {}   # guild_id -> {level: role_id}
autoreact_data    = {}   # channel_id -> emoji
boost_data        = {}   # guild_id -> {channel, message}
level_channel     = {}   # guild_id -> channel_id
muterole_data     = {}   # guild_id -> role_id

CODER_ID  = 1332107752352383020
BOT_START = datetime.datetime.utcnow()

CONFIG = {"xp_per_msg": 10, "xp_base": 100}

shop_items = {
    "vip":     {"price": 5000, "desc": "VIP badge for your profile"},
    "boost":   {"price": 2000, "desc": "2x XP for 1 hour"},
    "lootbox": {"price": 500,  "desc": "Random coin reward 100-1000"},
    "shield":  {"price": 1500, "desc": "Protects you from one robbery"},
    "ticket":  {"price": 250,  "desc": "A shiny collectible ticket"},
}


# ── EVENTS ─────────────────────────────────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Connected to {len(bot.guilds)} server(s)")
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="over the server | .help"
        )
    )
    reminder_check.start()
    birthday_check.start()


@bot.event
async def on_message(message):
    if message.author.bot:
        return

    now = datetime.datetime.utcnow()

    # Auto-react
    if message.channel.id in autoreact_data:
        try:
            await message.add_reaction(autoreact_data[message.channel.id])
        except Exception:
            pass

    # AFK mention check
    for mentioned in message.mentions:
        if mentioned.id in afk_data:
            reason, _ = afk_data[mentioned.id]
            await message.channel.send(
                f"💤 **{mentioned.display_name}** is AFK: {reason}",
                delete_after=10
            )

    # AFK return
    if message.author.id in afk_data:
        del afk_data[message.author.id]
        await message.channel.send(
            f"✅ Welcome back {message.author.mention}! AFK removed.",
            delete_after=5
        )

    low = message.content.lower()
    for word in blacklisted_words:
        if word in low:
            await message.delete()
            await message.channel.send(
                f"🚫 {message.author.mention}, that word is not allowed.",
                delete_after=5
            )
            return

    # Anti-spam (6 msgs in 5s)
    uid = message.author.id
    spam_tracker[uid] = [t for t in spam_tracker[uid] if now.timestamp() - t < 5]
    spam_tracker[uid].append(now.timestamp())
    if len(spam_tracker[uid]) >= 6:
        await message.delete()
        await message.channel.send(
            f"⚠️ {message.author.mention}, slow down!",
            delete_after=5
        )
        return

    # Counting game
    if message.guild and message.guild.id in counting_data:
        cdata = counting_data[message.guild.id]
        if message.channel.id == cdata.get("channel"):
            try:
                num = int(message.content.strip())
                if num == cdata["count"] + 1:
                    counting_data[message.guild.id]["count"] = num
                    await message.add_reaction("✅")
                else:
                    prev = cdata["count"]
                    counting_data[message.guild.id]["count"] = 0
                    await message.channel.send(
                        f"❌ {message.author.mention} ruined it at **{prev}**! Resetting to 0."
                    )
            except ValueError:
                pass

    # XP system
    xp_data[uid] += CONFIG["xp_per_msg"]
    required = (level_data[uid] + 1) * CONFIG["xp_base"]
    if xp_data[uid] >= required:
        level_data[uid] += 1
        xp_data[uid] = 0
        new_level = level_data[uid]
        # Level-up announcement
        if message.guild and message.guild.id in level_channel:
            ch = bot.get_channel(level_channel[message.guild.id])
            if ch:
                await ch.send(f"🎉 {message.author.mention} reached **Level {new_level}**!")
        # Level role reward
        if message.guild and message.guild.id in level_roles:
            rid = level_roles[message.guild.id].get(new_level)
            if rid:
                role = message.guild.get_role(rid)
                if role:
                    try:
                        await message.author.add_roles(role)
                    except Exception:
                        pass

    # Sticky messages
    if message.guild and message.channel.id in sticky_messages:
        sticky = sticky_messages[message.channel.id]
        if sticky.get("last_msg"):
            try:
                old = await message.channel.fetch_message(sticky["last_msg"])
                await old.delete()
            except Exception:
                pass
        sent = await message.channel.send(f"📌 **Sticky:** {sticky['content']}")
        sticky_messages[message.channel.id]["last_msg"] = sent.id

    await bot.process_commands(message)


@bot.event
async def on_message_delete(message):
    if not message.author.bot:
        snipe_data[message.channel.id] = message


@bot.event
async def on_message_edit(before, after):
    if not before.author.bot:
        edit_snipe_data[before.channel.id] = (before, after)


@bot.event
async def on_member_join(member):
    guild = member.guild

    if guild.id in autorole_data:
        role = guild.get_role(autorole_data[guild.id])
        if role:
            try:
                await member.add_roles(role)
            except Exception:
                pass

    if guild.id in join_logs:
        ch = bot.get_channel(join_logs[guild.id])
        if ch:
            embed = discord.Embed(
                title="👋 Member Joined",
                color=discord.Color.green(),
                timestamp=datetime.datetime.utcnow()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.add_field(name="Member", value=str(member))
            embed.add_field(name="ID", value=str(member.id))
            embed.add_field(name="Account Created", value=member.created_at.strftime("%Y-%m-%d"))
            embed.add_field(name="Member Count", value=str(guild.member_count))
            await ch.send(embed=embed)

    if guild.id in welcome_data:
        wdata = welcome_data[guild.id]
        ch = bot.get_channel(wdata["channel"])
        if ch:
            msg = (
                wdata["message"]
                .replace("{user}", member.mention)
                .replace("{server}", guild.name)
                .replace("{count}", str(guild.member_count))
            )
            await ch.send(msg)


@bot.event
async def on_member_remove(member):
    guild = member.guild

    if guild.id in join_logs:
        ch = bot.get_channel(join_logs[guild.id])
        if ch:
            embed = discord.Embed(
                title="👋 Member Left",
                description=f"**{member}** left the server.",
                color=discord.Color.red(),
                timestamp=datetime.datetime.utcnow()
            )
            await ch.send(embed=embed)

    if guild.id in goodbye_data:
        gdata = goodbye_data[guild.id]
        ch = bot.get_channel(gdata["channel"])
        if ch:
            msg = (
                gdata["message"]
                .replace("{user}", str(member))
                .replace("{server}", guild.name)
            )
            await ch.send(msg)


@bot.event
async def on_member_update(before, after):
    # Boost message
    if not before.guild:
        return
    if after.guild.id in boost_data:
        was = before.premium_since
        now_b = after.premium_since
        if was is None and now_b is not None:
            data = boost_data[after.guild.id]
            ch = bot.get_channel(data["channel"])
            if ch:
                await ch.send(data["message"].replace("{user}", after.mention).replace("{server}", after.guild.name))


@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    msg_id = reaction.message.id

    # Reaction roles
    if msg_id in reaction_roles:
        emoji_str = str(reaction.emoji)
        if emoji_str in reaction_roles[msg_id]:
            role = reaction.message.guild.get_role(reaction_roles[msg_id][emoji_str])
            if role:
                try:
                    await user.add_roles(role)
                except Exception:
                    pass

    # Starboard
    threshold = 3
    if reaction.message.guild and reaction.message.guild.id in starboard_data:
        threshold = starboard_data.get("_count_" + str(reaction.message.guild.id), 3)
    if str(reaction.emoji) == "⭐" and reaction.count >= threshold:
        guild = reaction.message.guild
        if guild and guild.id in starboard_data and msg_id not in starboard_posted:
            sb_ch = bot.get_channel(starboard_data[guild.id])
            if sb_ch:
                embed = discord.Embed(
                    description=reaction.message.content or "*No text*",
                    color=discord.Color.gold(),
                    timestamp=reaction.message.created_at
                )
                embed.set_author(
                    name=str(reaction.message.author),
                    icon_url=reaction.message.author.display_avatar.url
                )
                embed.add_field(name="Source", value=f"[Jump]({reaction.message.jump_url})")
                if reaction.message.attachments:
                    embed.set_image(url=reaction.message.attachments[0].url)
                await sb_ch.send(
                    f"⭐ **{reaction.count}** | {reaction.message.channel.mention}",
                    embed=embed
                )
                starboard_posted.add(msg_id)


@bot.event
async def on_reaction_remove(reaction, user):
    if user.bot:
        return
    msg_id = reaction.message.id
    if msg_id in reaction_roles:
        emoji_str = str(reaction.emoji)
        if emoji_str in reaction_roles[msg_id]:
            role = reaction.message.guild.get_role(reaction_roles[msg_id][emoji_str])
            if role:
                try:
                    await user.remove_roles(role)
                except Exception:
                    pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("❌ You don't have permission.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing: `{error.param.name}`")
    elif isinstance(error, commands.MemberNotFound):
        await ctx.send("❌ Member not found.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("❌ Invalid argument.")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"⏳ Cooldown! Try in `{error.retry_after:.1f}s`.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    else:
        await ctx.send(f"❌ Error: `{error}`")


# ── TASKS ──────────────────────────────────────────────────────────────────────
@tasks.loop(seconds=30)
async def reminder_check():
    now = datetime.datetime.utcnow()
    for r in reminder_data[:]:
        if now >= r["time"]:
            ch = bot.get_channel(r["channel_id"])
            u = bot.get_user(r["user_id"])
            if ch and u:
                await ch.send(f"⏰ {u.mention} Reminder: **{r['message']}**")
            reminder_data.remove(r)


@tasks.loop(hours=24)
async def birthday_check():
    today = datetime.datetime.utcnow().strftime("%m-%d")
    for uid, data in birthday_data.items():
        if data["date"] == today:
            ch = bot.get_channel(data.get("channel", 0))
            u = bot.get_user(uid)
            if ch and u:
                await ch.send(f"🎂 Happy Birthday {u.mention}! 🎉🥳")


# ── HELP COMMAND ───────────────────────────────────────────────────────────────
CATEGORY_TAGLINES = {
    "moderation": "Maintain order with grace and authority.",
    "security":   "Precision tools of protection and discretion.",
    "fun":        "Delight your server with a touch of flair.",
    "utility":    "Refined tools for everyday elegance.",
    "economy":    "Fortune favors the well-equipped.",
    "levels":     "Climb the ranks in style.",
    "server":     "Curate your server's finest details.",
    "info":       "Everything worth knowing, beautifully presented.",
}

HELP_DIVIDER = "⎯" * 38


@bot.command()
async def help(ctx, category: str = None):
    categories = {
        "moderation": {"emoji": "🛡️", "color": discord.Color(0x922B21), "commands": [
            (".kick @user [reason]", "Kick a member"),
            (".ban @user [reason]", "Ban a member"),
            (".unban <user_id>", "Unban a user by ID"),
            (".mute @user <min>", "Timeout a member"),
            (".unmute @user", "Remove a timeout"),
            (".timeout @user <min>", "Timeout a member (alias)"),
            (".untimeout @user", "Remove timeout (alias)"),
            (".warn @user <reason>", "Warn a member"),
            (".warnings [@user]", "View warnings"),
            (".warninfo @user <n>", "View a specific warning"),
            (".warncount [@user]", "Count a member's warnings"),
            (".unwarn @user <n>", "Remove one warning"),
            (".clearwarns @user", "Clear all warnings"),
            (".warnlist", "Members with warnings"),
            (".purge <1-100>", "Bulk delete messages"),
            (".cleanbot [n]", "Delete recent bot messages"),
            (".cleanuser @user [n]", "Delete a user's messages"),
            (".purgelinks [n]", "Delete messages with links"),
            (".purgeimages [n]", "Delete messages with images"),
            (".clearreactions <msg_id>", "Clear reactions on a message"),
            (".slowmode <sec>", "Set channel slowmode"),
            (".slowoff", "Disable slowmode"),
            (".lock", "Lock the channel"),
            (".unlock", "Unlock the channel"),
            (".hide", "Hide channel from @everyone"),
            (".unhide", "Reveal channel to @everyone"),
            (".lockdown", "Lock ALL channels"),
            (".unlockdown", "Unlock ALL channels"),
            (".nickname @user <name>", "Change a nickname"),
            (".resetnick @user", "Reset a nickname"),
            (".dehoist @user", "Strip hoisting chars from nick"),
            (".addrole @user <role>", "Add a role"),
            (".removerole @user <role>", "Remove a role"),
            (".createrole <name>", "Create a role"),
            (".deleterole <role>", "Delete a role"),
            (".voicekick @user", "Disconnect from voice"),
            (".voicemute @user", "Server-mute in voice"),
            (".voiceunmute @user", "Server-unmute in voice"),
            (".deafen @user", "Server-deafen"),
            (".undeafen @user", "Server-undeafen"),
            (".moveall <#voice>", "Move all voice members"),
            (".pin <msg_id>", "Pin a message"),
            (".unpin <msg_id>", "Unpin a message"),
            (".settopic <text>", "Set channel topic"),
            (".renamechannel <name>", "Rename current channel"),
            (".nuke", "Clone+delete channel (clear)"),
            (".softban @user [reason]", "Ban+unban to clear messages"),
            (".massban <ids...>", "Ban multiple users"),
            (".unbanall", "Unban everyone"),
            (".banlist", "View banned users"),
            (".baninfo <user_id>", "Why a user was banned"),
            (".mutelist", "Currently timed-out members"),
        ]},
        "security": {"emoji": "🔒", "color": discord.Color(0x1B4F72), "commands": [
            (".addword <word>", "Blacklist a word"),
            (".removeword <word>", "Unblacklist a word"),
            (".blacklist", "Show blacklist"),
            (".clearblacklist", "Clear blacklist"),
            (".antispam", "Anti-spam status"),
            (".hash <text>", "SHA-256 hash"),
            (".sha1 <text>", "SHA-1 hash"),
            (".sha512 <text>", "SHA-512 hash"),
            (".md5 <text>", "MD5 hash"),
            (".crc32 <text>", "CRC32 checksum"),
            (".fingerprint <text>", "Short fingerprint hash"),
            (".encode <text>", "Base64 encode"),
            (".decode <text>", "Base64 decode"),
            (".base32 <text>", "Base32 encode"),
            (".base32decode <text>", "Base32 decode"),
            (".hexencode <text>", "Text to hex"),
            (".hexdecode <text>", "Hex to text"),
            (".binary <text>", "Text to binary"),
            (".unbinary <bits>", "Binary to text"),
            (".rot13 <text>", "ROT13 cipher"),
            (".caesar <shift> <text>", "Caesar cipher"),
            (".atbash <text>", "Atbash cipher"),
            (".leet <text>", "Leetspeak"),
            (".morse <text>", "Text to Morse"),
            (".unmorse <morse>", "Morse to text"),
            (".urlencode <text>", "URL encode"),
            (".urldecode <text>", "URL decode"),
            (".jwtdecode <token>", "Decode a JWT payload"),
            (".entropy <text>", "Shannon entropy"),
            (".luhn <number>", "Validate Luhn checksum"),
            (".validemail <text>", "Validate an email"),
            (".validurl <text>", "Validate a URL"),
            (".uuidgen", "Generate a UUID"),
            (".token [len]", "Random secure token"),
            (".genpin [len]", "Random numeric PIN"),
            (".randstr [len]", "Random string"),
            (".passphrase [words]", "Word passphrase"),
            (".randmac", "Random MAC address"),
            (".maskip <ip>", "Mask an IP's last octet"),
            (".nslookup <domain>", "Resolve a domain"),
            (".portinfo <port>", "Common port info"),
            (".useragent", "Random user-agent"),
            (".pwcheck <password>", "Rate password strength"),
            (".pwgen [length]", "Generate a password (DM)"),
            (".permissions [@user]", "List permissions"),
            (".serverinfo", "Server statistics"),
            (".userinfo [@user]", "Member profile"),
            (".roleinfo <role>", "Role details"),
            (".channelinfo [#ch]", "Channel details"),
            (".ipinfo <ip>", "Geo-lookup an IP"),
            (".inviteinfo <code>", "Inspect an invite"),
            (".botinfo", "Bot info"),
            (".banlist", "Banned users"),
        ]},
        "fun": {"emoji": "🎉", "color": discord.Color(0x6C3483), "commands": [
            (".8ball <q>", "Magic 8-ball"),
            (".roll <NdS>", "Roll dice"),
            (".coinflip", "Flip a coin"),
            (".rps <choice>", "Rock paper scissors"),
            (".joke", "Random joke"),
            (".roast @user", "Roast someone"),
            (".compliment @user", "Compliment someone"),
            (".pickup @user", "Pickup line"),
            (".ship @user1 @user2", "Compatibility"),
            (".marry @user", "Propose"),
            (".rate <thing>", "Rate /10"),
            (".chance <thing>", "Percent chance"),
            (".yesno <q>", "Yes or no"),
            (".reverse <text>", "Reverse text"),
            (".mock <text>", "MoCk TeXt"),
            (".clap <text>", "Add 👏 claps"),
            (".owoify <text>", "OwO-ify text"),
            (".emojify <text>", "Regional-indicator text"),
            (".vaporwave <text>", "Ｆｕｌｌｗｉｄｔｈ"),
            (".ascii <text>", "Spaced caps"),
            (".trivia", "Trivia (+50 XP)"),
            (".scramble", "Word scramble (+30 XP)"),
            (".guessnum", "Guess the number"),
            (".enlarge <emoji>", "Enlarge custom emoji"),
            (".hug @user", "Hug someone"),
            (".slap @user", "Slap someone"),
            (".punch @user", "Punch someone"),
            (".kiss @user", "Kiss someone"),
            (".pat @user", "Pat someone"),
            (".highfive @user", "High-five"),
            (".bonk @user", "Bonk someone"),
            (".cookie @user", "Give a cookie"),
            (".kill @user", "Dramatic (fictional)"),
            (".howgay [@user]", "Gay rating"),
            (".howcringe [@user]", "Cringe rating"),
            (".howbased [@user]", "Based rating"),
            (".howedgy [@user]", "Edgy rating"),
            (".howcool [@user]", "Cool rating"),
            (".howrich [@user]", "Rich rating"),
            (".howlucky [@user]", "Luck rating"),
            (".howhot [@user]", "Hot rating"),
            (".howfunny [@user]", "Funny rating"),
            (".pp [@user]", "PP size"),
            (".iq [@user]", "IQ result"),
            (".simp [@user]", "Simp rating"),
            (".sus [@user]", "Sus meter"),
            (".vibe [@user]", "Vibe check"),
            (".fortune", "Fortune cookie"),
            (".fact", "Random fact"),
            (".catfact", "Cat fact"),
            (".quote", "Inspirational quote"),
            (".advice", "Random advice"),
            (".excuse", "Random excuse"),
            (".wouldyourather", "Would you rather"),
            (".neverhaveiever", "Never have I ever"),
            (".thisorthat", "This or that"),
            (".truth", "Truth"),
            (".dare", "Dare"),
        ]},
        "utility": {"emoji": "🔧", "color": discord.Color(0x117A65), "commands": [
            (".afk [reason]", "Set AFK"),
            (".remind <min> <msg>", "Set a reminder"),
            (".snipe", "Last deleted message"),
            (".editsnipe", "Last edited message"),
            (".poll Q | A | B", "Reaction poll"),
            (".quickpoll <q>", "Yes/no poll"),
            (".note <text>", "Save a note"),
            (".notes", "View notes"),
            (".deletenote <n>", "Delete a note"),
            (".clearnotes", "Delete all notes"),
            (".todo <text>", "Add a to-do"),
            (".todos", "View to-dos"),
            (".donetodo <n>", "Complete a to-do"),
            (".avatar [@user]", "Member avatar"),
            (".banner [@user]", "Member banner"),
            (".ping", "Bot latency"),
            (".uptime", "Bot uptime"),
            (".timestamp", "Current UTC time"),
            (".math <expr>", "Calculator"),
            (".calculator <expr>", "Calculator (alias)"),
            (".wordcount <text>", "Count words"),
            (".charcount <text>", "Count characters"),
            (".upper <text>", "UPPERCASE"),
            (".lower <text>", "lowercase"),
            (".titlecase <text>", "Title Case"),
            (".repeat <n> <text>", "Repeat text"),
            (".randomnumber <a> <b>", "Random number"),
            (".roman <number>", "To Roman numerals"),
            (".unroman <roman>", "From Roman numerals"),
            (".tobinary <number>", "Decimal to binary"),
            (".tohex <number>", "Decimal to hex"),
            (".tooct <number>", "Decimal to octal"),
            (".factorial <n>", "n!"),
            (".fibonacci <n>", "nth Fibonacci"),
            (".isprime <n>", "Prime check"),
            (".gcd <a> <b>", "Greatest common divisor"),
            (".lcm <a> <b>", "Least common multiple"),
            (".average <nums>", "Average of numbers"),
            (".percentof <a> <b>", "a% of b"),
            (".tip <amt> <pct>", "Tip calculator"),
            (".temp <val><C/F>", "Temperature convert"),
            (".age <YYYY-MM-DD>", "Age from date"),
            (".daysuntil <YYYY-MM-DD>", "Days until date"),
            (".nato <text>", "NATO phonetic"),
            (".urban <word>", "Urban Dictionary"),
            (".define <word>", "Dictionary lookup"),
            (".color <hex>", "Preview hex color"),
            (".qr <text>", "Generate QR code"),
            (".timer <sec>", "Countdown timer"),
            (".choose a | b", "Bot picks one"),
            (".tag <name>", "Get a tag"),
            (".addtag name | content", "Save a tag"),
            (".deltag <name>", "Delete a tag"),
            (".tags", "List tags"),
        ]},
        "economy": {"emoji": "💰", "color": discord.Color(0xD4AF37), "commands": [
            (".balance [@user]", "Wallet + bank"),
            (".networth [@user]", "Total net worth"),
            (".daily", "Claim daily"),
            (".weekly", "Claim weekly"),
            (".monthly", "Claim monthly"),
            (".hourly", "Claim hourly"),
            (".work", "Work for coins"),
            (".beg", "Beg for coins"),
            (".dig", "Dig for coins"),
            (".fish", "Go fishing"),
            (".hunt", "Go hunting"),
            (".mine", "Mine for coins"),
            (".search", "Search for coins"),
            (".scavenge", "Scavenge for coins"),
            (".crime", "Commit a crime (risky)"),
            (".quest", "Complete a quest"),
            (".give @user <amt>", "Transfer coins"),
            (".gift @user <item>", "Gift an item"),
            (".rob @user", "Rob someone"),
            (".heist @user", "Heist together"),
            (".leaderboard", "Richest members"),
            (".poorest", "Poorest members"),
            (".slots [bet]", "Slot machine"),
            (".gamble <amt>", "Double or nothing"),
            (".flip <amt>", "Coinflip gamble"),
            (".dicebet <amt>", "Dice gamble"),
            (".blackjack <amt>", "Blackjack"),
            (".roulette <amt> <color>", "Roulette"),
            (".highlow <amt>", "Higher or lower"),
            (".scratch <amt>", "Scratch card"),
            (".wheel <amt>", "Wheel of fortune"),
            (".invest <amt>", "Invest for returns"),
            (".stocks", "View stock prices"),
            (".deposit <amt>", "Deposit to bank"),
            (".withdraw <amt>", "Withdraw from bank"),
            (".bankbalance", "Bank balance"),
            (".interest", "Claim bank interest"),
            (".shop", "View shop"),
            (".buy <item>", "Buy an item"),
            (".sell <item>", "Sell an item"),
            (".use <item>", "Use an item"),
            (".inventory", "View items"),
            (".lottery", "Buy lottery ticket"),
            (".jackpot", "View lottery pot"),
            (".drawlottery", "Draw winner (admin)"),
            (".coinrain <amt>", "Rain coins (admin)"),
            (".addcoins @user <amt>", "Add coins (admin)"),
            (".removecoins @user <amt>", "Remove coins (admin)"),
            (".setcoins @user <amt>", "Set coins (admin)"),
            (".resetcoins @user", "Reset wallet (admin)"),
            (".resetbank @user", "Reset bank (admin)"),
        ]},
        "levels": {"emoji": "⭐", "color": discord.Color(0xB76E79), "commands": [
            (".level [@user]", "Level + progress"),
            (".lvl [@user]", "Level (alias)"),
            (".levelcheck [@user]", "Level (alias)"),
            (".levelof [@user]", "Just the level"),
            (".rank [@user]", "Server rank"),
            (".rankof [@user]", "Rank (alias)"),
            (".myrank", "Your rank"),
            (".mylevel", "Your level"),
            (".myxp", "Your XP"),
            (".xp [@user]", "XP + level"),
            (".exp [@user]", "XP (alias)"),
            (".experience [@user]", "XP (alias)"),
            (".xpinfo [@user]", "Detailed XP info"),
            (".nextlevel [@user]", "XP to next level"),
            (".xpneeded [@user]", "XP needed (alias)"),
            (".levelprogress [@user]", "Progress %"),
            (".progressbar [@user]", "Progress bar"),
            (".rankcard [@user]", "Rank card"),
            (".top", "Top by level"),
            (".toplevels", "Top by level (alias)"),
            (".levelboard", "Level leaderboard"),
            (".bottomlevels", "Lowest levels"),
            (".xpboard", "Top by XP"),
            (".xpleaderboard", "Top by XP (alias)"),
            (".highestlevel", "Highest member"),
            (".lowestlevel", "Lowest member"),
            (".averagelevel", "Average level"),
            (".totalxp", "Total server XP"),
            (".levelstats", "Level statistics"),
            (".whoislevel <n>", "Members at a level"),
            (".givexp @user <amt>", "Give XP (admin)"),
            (".addxp @user <amt>", "Add XP (admin)"),
            (".removexp @user <amt>", "Remove XP (admin)"),
            (".setxp @user <amt>", "Set XP (admin)"),
            (".addlevel @user <n>", "Add levels (admin)"),
            (".removelevel @user <n>", "Remove levels (admin)"),
            (".givelevel @user <n>", "Give levels (admin)"),
            (".setlevel @user <n>", "Set level (admin)"),
            (".maxlevel @user", "Set to level 100 (admin)"),
            (".resetxp @user", "Reset member (admin)"),
            (".resetlevel @user", "Reset member (admin)"),
            (".resetallxp", "Reset all XP (admin)"),
            (".resetalllevels", "Reset all levels (admin)"),
            (".setlevelrole <n> <role>", "Reward role (admin)"),
            (".removelevelrole <n>", "Remove reward (admin)"),
            (".levelroles", "List reward roles"),
            (".clearlevelroles", "Clear rewards (admin)"),
            (".setxpgain <amt>", "XP per message (admin)"),
            (".setbasexp <amt>", "XP per level (admin)"),
            (".xpconfig", "Show XP config"),
            (".resetxpconfig", "Reset XP config (admin)"),
        ]},
        "server": {"emoji": "⚙️", "color": discord.Color(0x0B5345), "commands": [
            (".setjoinlog #ch", "Set join/leave log"),
            (".removejoinlog", "Remove join/leave log"),
            (".autorole <role>", "Auto-assign role"),
            (".removeautorole", "Remove auto-role"),
            (".setwelcome #ch <msg>", "Set welcome message"),
            (".removewelcome", "Remove welcome"),
            (".setgoodbye #ch <msg>", "Set goodbye message"),
            (".removegoodbye", "Remove goodbye"),
            (".setboost #ch <msg>", "Set boost message"),
            (".removeboost", "Remove boost message"),
            (".setlevelchannel #ch", "Set level-up channel"),
            (".removelevelchannel", "Remove level-up channel"),
            (".setmuterole <role>", "Set mute role"),
            (".setautoreact #ch <emoji>", "Auto-react in channel"),
            (".removeautoreact #ch", "Stop auto-react"),
            (".giveaway <min> <prize>", "Start a giveaway"),
            (".greroll <msg_id>", "Reroll giveaway"),
            (".announce #ch <msg>", "Styled announcement"),
            (".embed Title | Desc", "Custom embed"),
            (".say <msg>", "Bot speaks"),
            (".dm @user <msg>", "DM a member (admin)"),
            (".sticky <msg>", "Sticky message"),
            (".unsticky", "Remove sticky"),
            (".reactionrole <id> <emoji> <r>", "Add reaction role"),
            (".removereactionrole <id>", "Remove reaction roles"),
            (".reactionroles", "List reaction roles"),
            (".setstarboard #ch", "Set starboard"),
            (".removestarboard", "Remove starboard"),
            (".setstarcount <n>", "Stars needed"),
            (".setcounting #ch", "Start counting game"),
            (".removecounting", "Stop counting game"),
            (".resetcounting", "Reset counter to 0"),
            (".countstatus", "Current count"),
            (".setlogchannel #ch", "Set mod log"),
            (".removelogchannel", "Remove mod log"),
            (".confession #ch", "Set confession channel"),
            (".confess <text>", "Anonymous confession"),
            (".removeconfession", "Remove confession ch"),
            (".suggest #ch", "Set suggestion channel"),
            (".suggest_idea <text>", "Submit a suggestion"),
            (".removesuggestion", "Remove suggestion ch"),
            (".setbirthday MM-DD", "Register birthday"),
            (".removebirthday", "Remove your birthday"),
            (".birthdays", "List birthdays"),
            (".nextbirthday", "Next upcoming birthday"),
            (".birthdaycount", "Registered birthdays count"),
            (".clone #ch", "Clone a channel"),
            (".createcategory <name>", "Create a category"),
            (".createvoicechannel <name>", "Create a voice channel"),
            (".setservername <name>", "Rename the server"),
            (".settings", "Show server config"),
        ]},
        "info": {"emoji": "📊", "color": discord.Color(0x1F618D), "commands": [
            (".membercount", "Member breakdown"),
            (".humancount", "Human count"),
            (".botcount", "Bot count"),
            (".onlinecount", "Online count"),
            (".statuscount", "Status breakdown"),
            (".botstats", "Bot statistics"),
            (".botinfo", "Bot info"),
            (".rolecount", "Members per role"),
            (".rolelist", "List roles"),
            (".biggestrole", "Most-populated role"),
            (".smallestrole", "Least-populated role"),
            (".emptyroles", "Roles with 0 members"),
            (".norole", "Members with no role"),
            (".hasrole @user <role>", "Check a role"),
            (".toprole [@user]", "Highest role"),
            (".colorof [@user]", "Member color"),
            (".inrole <role>", "Members in a role"),
            (".channelcount", "Channel counts"),
            (".textchannels", "List text channels"),
            (".voicechannels", "List voice channels"),
            (".categories", "List categories"),
            (".channelid [#ch]", "Channel ID"),
            (".emojilist", "List emojis"),
            (".emojicount", "Emoji count"),
            (".stickers", "List stickers"),
            (".stickercount", "Sticker count"),
            (".admins", "List admins"),
            (".mods", "List moderators"),
            (".bots", "List bots"),
            (".owner", "Server owner"),
            (".serverage", "Server age"),
            (".serverinfo", "Server stats"),
            (".servericon", "Server icon"),
            (".serverbanner", "Server banner"),
            (".vanity", "Vanity invite"),
            (".features", "Guild features"),
            (".verificationlevel", "Verification level"),
            (".afkchannel", "AFK channel"),
            (".systemchannel", "System channel"),
            (".boostcount", "Boost count"),
            (".boostlevel", "Boost tier"),
            (".boosters", "List boosters"),
            (".oldest", "Oldest accounts"),
            (".newest", "Newest members"),
            (".firstjoined", "First member to join"),
            (".accountage [@user]", "Account age"),
            (".joinposition [@user]", "Join order"),
            (".joinedat [@user]", "Join date"),
            (".createdat [@user]", "Account creation date"),
            (".avatarurl [@user]", "Raw avatar URL"),
            (".bannerurl [@user]", "Raw banner URL"),
            (".invites [@user]", "Invite count"),
        ]},
    }

    if category and category.lower() in categories:
        cat = category.lower()
        data = categories[cat]
        cmds = data["commands"]
        chunks = [cmds[i:i + 24] for i in range(0, len(cmds), 24)]
        tagline = CATEGORY_TAGLINES.get(cat, "")

        for idx, chunk in enumerate(chunks):
            page = list(chunk)
            while len(page) % 3 != 0:
                page.append((None, None))

            title = f"✦ {data['emoji']}  {cat.upper()}  {data['emoji']} ✦"
            if len(chunks) > 1:
                title += f"   ·   Page {idx + 1}/{len(chunks)}"
            page_desc = f"*{tagline}*\n{HELP_DIVIDER}" if idx == 0 else HELP_DIVIDER

            embed = discord.Embed(title=title, description=page_desc, color=data["color"])
            for cmd, desc_text in page:
                if cmd is None:
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                else:
                    embed.add_field(name=f"`{cmd}`", value=f"*{desc_text}*", inline=True)

            embed.set_thumbnail(url=bot.user.display_avatar.url)
            embed.set_footer(text="✦ Em-Bot Prestige Suite ✦  Use .help for all categories  |  Prefix: .")
            await ctx.send(embed=embed)
    else:
        total = sum(len(d["commands"]) for d in categories.values())
        embed = discord.Embed(
            title="👑  Em-Bot — Prestige Command Suite  👑",
            description=(
                f"*A curated collection of* **{total} commands** *across* **{len(categories)} categories**.\n"
                f"Use `.help <category>` to explore a collection in full.\n{HELP_DIVIDER}"
            ),
            color=discord.Color(0xD4AF37)
        )
        for cat, data in categories.items():
            embed.add_field(
                name=f"{data['emoji']}  {cat.capitalize()}",
                value=f"*{CATEGORY_TAGLINES.get(cat, '')}*\n`{len(data['commands'])} commands`  ·  `.help {cat}`",
                inline=True
            )
        while len(embed.fields) % 3 != 0:
            embed.add_field(name="\u200b", value="\u200b", inline=True)

        if ctx.guild and ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        embed.set_footer(
            text=f"Requested by {ctx.author} ✦ {total} commands curated for you",
            icon_url=ctx.author.display_avatar.url
        )
        await ctx.send(embed=embed)


# ── MODERATION ─────────────────────────────────────────────────────────────────
@bot.command()
@commands.has_permissions(kick_members=True)
async def kick(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.kick(reason=reason)
    embed = discord.Embed(title="👢 Member Kicked", color=discord.Color.orange())
    embed.add_field(name="Member", value=str(member))
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Moderator", value=str(ctx.author))
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(ban_members=True)
async def ban(ctx, member: discord.Member, *, reason="No reason provided"):
    await member.ban(reason=reason)
    embed = discord.Embed(title="🔨 Member Banned", color=discord.Color.red())
    embed.add_field(name="Member", value=str(member))
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Moderator", value=str(ctx.author))
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(ban_members=True)
async def unban(ctx, user_id: int):
    try:
        user = await bot.fetch_user(user_id)
        await ctx.guild.unban(user)
        await ctx.send(f"✅ **{user}** has been unbanned.")
    except Exception:
        await ctx.send("❌ User not found or not banned.")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def mute(ctx, member: discord.Member, minutes: int = 10, *, reason="No reason"):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    embed = discord.Embed(title="🔇 Member Muted", color=discord.Color.orange())
    embed.add_field(name="Member", value=str(member))
    embed.add_field(name="Duration", value=f"{minutes} minutes")
    embed.add_field(name="Reason", value=reason)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(moderate_members=True)
async def unmute(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"✅ **{member}** has been unmuted.")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def timeout(ctx, member: discord.Member, minutes: int = 10, *, reason="No reason"):
    await member.timeout(datetime.timedelta(minutes=minutes), reason=reason)
    await ctx.send(f"🔇 **{member}** timed out for **{minutes}** minutes.")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def untimeout(ctx, member: discord.Member):
    await member.timeout(None)
    await ctx.send(f"✅ **{member}**'s timeout removed.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def warn(ctx, member: discord.Member, *, reason):
    warn_data[member.id].append({
        "reason": reason,
        "mod": str(ctx.author),
        "time": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M")
    })
    count = len(warn_data[member.id])
    embed = discord.Embed(title="⚠️ Member Warned", color=discord.Color.yellow())
    embed.add_field(name="Member", value=str(member))
    embed.add_field(name="Reason", value=reason)
    embed.add_field(name="Total Warnings", value=str(count))
    await ctx.send(embed=embed)
    try:
        await member.send(f"⚠️ You were warned in **{ctx.guild.name}**: {reason}")
    except Exception:
        pass


@bot.command()
async def warnings(ctx, member: discord.Member = None):
    member = member or ctx.author
    warns = warn_data.get(member.id, [])
    if not warns:
        await ctx.send(f"✅ **{member}** has no warnings.")
        return
    embed = discord.Embed(title=f"⚠️ Warnings for {member}", color=discord.Color.yellow())
    for i, w in enumerate(warns, 1):
        embed.add_field(name=f"#{i}", value=f"**Reason:** {w['reason']}\n**By:** {w['mod']}\n**At:** {w['time']}", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def warninfo(ctx, member: discord.Member, number: int):
    warns = warn_data.get(member.id, [])
    if not 1 <= number <= len(warns):
        await ctx.send("❌ Invalid warning number.")
        return
    w = warns[number - 1]
    embed = discord.Embed(title=f"⚠️ Warning #{number} — {member}", color=discord.Color.yellow())
    embed.add_field(name="Reason", value=w["reason"], inline=False)
    embed.add_field(name="Moderator", value=w["mod"])
    embed.add_field(name="Date", value=w["time"])
    await ctx.send(embed=embed)


@bot.command()
async def warncount(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"⚠️ **{member.display_name}** has **{len(warn_data.get(member.id, []))}** warning(s).")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def unwarn(ctx, member: discord.Member, number: int):
    warns = warn_data.get(member.id, [])
    if not 1 <= number <= len(warns):
        await ctx.send("❌ Invalid warning number.")
        return
    removed = warns.pop(number - 1)
    await ctx.send(f"✅ Removed warning #{number} ({removed['reason']}) from **{member}**.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearwarns(ctx, member: discord.Member):
    warn_data[member.id] = []
    await ctx.send(f"✅ Cleared all warnings for **{member}**.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def warnlist(ctx):
    members_with_warns = [(uid, w) for uid, w in warn_data.items() if w]
    if not members_with_warns:
        await ctx.send("✅ No members have warnings.")
        return
    embed = discord.Embed(title="⚠️ All Warnings", color=discord.Color.yellow())
    for uid, warns in members_with_warns[:20]:
        user = bot.get_user(uid)
        name = str(user) if user else f"ID:{uid}"
        embed.add_field(name=name, value=f"{len(warns)} warning(s)", inline=True)
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def purge(ctx, amount: int):
    if not 1 <= amount <= 100:
        await ctx.send("❌ Amount must be 1-100.")
        return
    deleted = await ctx.channel.purge(limit=amount + 1)
    await ctx.send(f"🗑️ Deleted **{len(deleted)-1}** messages.", delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def cleanbot(ctx, amount: int = 50):
    deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.bot)
    await ctx.send(f"🧹 Removed **{len(deleted)}** bot messages.", delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def cleanuser(ctx, member: discord.Member, amount: int = 50):
    deleted = await ctx.channel.purge(limit=amount, check=lambda m: m.author.id == member.id)
    await ctx.send(f"🧹 Removed **{len(deleted)}** messages from **{member.display_name}**.", delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def purgelinks(ctx, amount: int = 50):
    deleted = await ctx.channel.purge(limit=amount, check=lambda m: "http://" in m.content or "https://" in m.content)
    await ctx.send(f"🧹 Removed **{len(deleted)}** messages with links.", delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def purgeimages(ctx, amount: int = 50):
    deleted = await ctx.channel.purge(limit=amount, check=lambda m: bool(m.attachments))
    await ctx.send(f"🧹 Removed **{len(deleted)}** messages with images.", delete_after=5)


@bot.command()
@commands.has_permissions(manage_messages=True)
async def clearreactions(ctx, message_id: int):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.clear_reactions()
        await ctx.send("✅ Reactions cleared.")
    except Exception:
        await ctx.send("❌ Message not found.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowmode(ctx, seconds: int):
    await ctx.channel.edit(slowmode_delay=seconds)
    msg = f"🐢 Slowmode set to **{seconds}s**." if seconds > 0 else "✅ Slowmode disabled."
    await ctx.send(msg)


@bot.command()
@commands.has_permissions(manage_channels=True)
async def slowoff(ctx):
    await ctx.channel.edit(slowmode_delay=0)
    await ctx.send("✅ Slowmode disabled.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def lock(ctx):
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.send_messages = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    locked_channels.add(ctx.channel.id)
    await ctx.send("🔒 Channel locked.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def unlock(ctx):
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.send_messages = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    locked_channels.discard(ctx.channel.id)
    await ctx.send("🔓 Channel unlocked.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def hide(ctx):
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.view_channel = False
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("🙈 Channel hidden from @everyone.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def unhide(ctx):
    ow = ctx.channel.overwrites_for(ctx.guild.default_role)
    ow.view_channel = True
    await ctx.channel.set_permissions(ctx.guild.default_role, overwrite=ow)
    await ctx.send("👁️ Channel revealed to @everyone.")


@bot.command()
@commands.has_permissions(administrator=True)
async def lockdown(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        ow = ch.overwrites_for(ctx.guild.default_role)
        ow.send_messages = False
        await ch.set_permissions(ctx.guild.default_role, overwrite=ow)
        count += 1
    await ctx.send(f"🔒 Server lockdown activated. Locked **{count}** channels.")


@bot.command()
@commands.has_permissions(administrator=True)
async def unlockdown(ctx):
    count = 0
    for ch in ctx.guild.text_channels:
        ow = ch.overwrites_for(ctx.guild.default_role)
        ow.send_messages = True
        await ch.set_permissions(ctx.guild.default_role, overwrite=ow)
        count += 1
    await ctx.send(f"🔓 Server lockdown lifted. Unlocked **{count}** channels.")


@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def nickname(ctx, member: discord.Member, *, name):
    await member.edit(nick=name)
    await ctx.send(f"✅ Nickname set to **{name}** for {member.mention}.")


@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def resetnick(ctx, member: discord.Member):
    await member.edit(nick=None)
    await ctx.send(f"✅ Reset nickname for {member.mention}.")


@bot.command()
@commands.has_permissions(manage_nicknames=True)
async def dehoist(ctx, member: discord.Member):
    name = member.display_name
    cleaned = name.lstrip("!\"#$%&'()*+,-./ ")
    cleaned = cleaned or "dehoisted"
    await member.edit(nick=cleaned)
    await ctx.send(f"✅ Dehoisted {member.mention} → **{cleaned}**.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def addrole(ctx, member: discord.Member, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    await member.add_roles(role)
    await ctx.send(f"✅ Added **{role.name}** to {member.mention}.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def removerole(ctx, member: discord.Member, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    await member.remove_roles(role)
    await ctx.send(f"✅ Removed **{role.name}** from {member.mention}.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def createrole(ctx, *, name):
    role = await ctx.guild.create_role(name=name)
    await ctx.send(f"✅ Created role **{role.name}**.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def deleterole(ctx, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    await role.delete()
    await ctx.send(f"🗑️ Deleted role **{role_name}**.")


@bot.command()
@commands.has_permissions(move_members=True)
async def voicekick(ctx, member: discord.Member):
    if member.voice:
        await member.move_to(None)
        await ctx.send(f"👢 Disconnected **{member.display_name}** from voice.")
    else:
        await ctx.send("❌ Member is not in a voice channel.")


@bot.command()
@commands.has_permissions(mute_members=True)
async def voicemute(ctx, member: discord.Member):
    await member.edit(mute=True)
    await ctx.send(f"🔇 Voice-muted **{member.display_name}**.")


@bot.command()
@commands.has_permissions(mute_members=True)
async def voiceunmute(ctx, member: discord.Member):
    await member.edit(mute=False)
    await ctx.send(f"🔊 Voice-unmuted **{member.display_name}**.")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def deafen(ctx, member: discord.Member):
    await member.edit(deafen=True)
    await ctx.send(f"🔇 Deafened **{member.display_name}**.")


@bot.command()
@commands.has_permissions(deafen_members=True)
async def undeafen(ctx, member: discord.Member):
    await member.edit(deafen=False)
    await ctx.send(f"🔊 Undeafened **{member.display_name}**.")


@bot.command()
@commands.has_permissions(move_members=True)
async def moveall(ctx, channel: discord.VoiceChannel):
    if not ctx.author.voice:
        await ctx.send("❌ You must be in a voice channel.")
        return
    moved = 0
    for m in ctx.author.voice.channel.members:
        await m.move_to(channel)
        moved += 1
    await ctx.send(f"➡️ Moved **{moved}** members to {channel.name}.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def pin(ctx, message_id: int):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.pin()
        await ctx.send("📌 Pinned.")
    except Exception:
        await ctx.send("❌ Message not found.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def unpin(ctx, message_id: int):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.unpin()
        await ctx.send("📌 Unpinned.")
    except Exception:
        await ctx.send("❌ Message not found.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def settopic(ctx, *, topic):
    await ctx.channel.edit(topic=topic)
    await ctx.send("✅ Channel topic updated.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def renamechannel(ctx, *, name):
    await ctx.channel.edit(name=name)
    await ctx.send(f"✅ Channel renamed to **{name}**.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def nuke(ctx):
    pos = ctx.channel.position
    new_ch = await ctx.channel.clone()
    await ctx.channel.delete()
    await new_ch.edit(position=pos)
    await new_ch.send("💥 Channel nuked — fresh start!")


@bot.command()
@commands.has_permissions(ban_members=True)
async def softban(ctx, member: discord.Member, *, reason="No reason"):
    await member.ban(reason=reason, delete_message_days=7)
    await ctx.guild.unban(member)
    await ctx.send(f"🔨 **{member}** was softbanned (messages cleared, immediately unbanned).")


@bot.command()
@commands.has_permissions(ban_members=True)
async def massban(ctx, *user_ids: int):
    count = 0
    for uid in user_ids:
        try:
            user = await bot.fetch_user(uid)
            await ctx.guild.ban(user)
            count += 1
        except Exception:
            pass
    await ctx.send(f"🔨 Mass banned **{count}** users.")


@bot.command()
@commands.has_permissions(ban_members=True)
async def unbanall(ctx):
    count = 0
    async for entry in ctx.guild.bans():
        await ctx.guild.unban(entry.user)
        count += 1
    await ctx.send(f"✅ Unbanned **{count}** users.")


@bot.command()
@commands.has_permissions(ban_members=True)
async def banlist(ctx):
    bans = [e async for e in ctx.guild.bans()]
    if not bans:
        await ctx.send("✅ No banned users.")
        return
    text = "\n".join(f"• {e.user} (`{e.user.id}`)" for e in bans[:20])
    embed = discord.Embed(title="🔨 Banned Users", description=text, color=discord.Color.red())
    embed.set_footer(text=f"Total: {len(bans)}")
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(ban_members=True)
async def baninfo(ctx, user_id: int):
    try:
        entry = await ctx.guild.fetch_ban(discord.Object(id=user_id))
        embed = discord.Embed(title="🔨 Ban Info", color=discord.Color.red())
        embed.add_field(name="User", value=str(entry.user))
        embed.add_field(name="Reason", value=entry.reason or "No reason")
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ User is not banned.")


@bot.command()
@commands.has_permissions(moderate_members=True)
async def mutelist(ctx):
    muted = [m for m in ctx.guild.members if m.timed_out_until and m.timed_out_until > datetime.datetime.now(datetime.timezone.utc)]
    if not muted:
        await ctx.send("✅ No members are timed out.")
        return
    text = "\n".join(f"• {m.display_name}" for m in muted[:20])
    embed = discord.Embed(title="🔇 Timed-out Members", description=text, color=discord.Color.orange())
    await ctx.send(embed=embed)


# ── SECURITY ───────────────────────────────────────────────────────────────────
MORSE_CODE = {
    'a':'.-','b':'-...','c':'-.-.','d':'-..','e':'.','f':'..-.','g':'--.','h':'....',
    'i':'..','j':'.---','k':'-.-','l':'.-..','m':'--','n':'-.','o':'---','p':'.--.',
    'q':'--.-','r':'.-.','s':'...','t':'-','u':'..-','v':'...-','w':'.--','x':'-..-',
    'y':'-.--','z':'--..','0':'-----','1':'.----','2':'..---','3':'...--','4':'....-',
    '5':'.....','6':'-....','7':'--...','8':'---..','9':'----.',' ':'/'
}
MORSE_REV = {v: k for k, v in MORSE_CODE.items()}


@bot.command()
@commands.has_permissions(manage_messages=True)
async def addword(ctx, *, word):
    blacklisted_words.add(word.lower())
    await ctx.send(f"✅ `{word}` added to blacklist.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def removeword(ctx, *, word):
    blacklisted_words.discard(word.lower())
    await ctx.send(f"✅ `{word}` removed from blacklist.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def blacklist(ctx):
    if not blacklisted_words:
        await ctx.send("✅ No blacklisted words.")
        return
    embed = discord.Embed(title="🚫 Blacklisted Words", description=", ".join(f"`{w}`" for w in blacklisted_words), color=discord.Color.red())
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def clearblacklist(ctx):
    blacklisted_words.clear()
    await ctx.send("✅ Blacklist cleared.")


@bot.command()
async def antispam(ctx):
    embed = discord.Embed(title="🛡️ Anti-Spam Status", color=discord.Color.green())
    embed.add_field(name="Status", value="✅ Active")
    embed.add_field(name="Threshold", value="6 messages / 5 seconds")
    embed.add_field(name="Action", value="Message deleted + warning")
    await ctx.send(embed=embed)


def _hash_embed(title, text, result, color):
    embed = discord.Embed(title=title, color=color)
    embed.add_field(name="Input", value=f"`{text[:80]}`", inline=False)
    embed.add_field(name="Output", value=f"`{result}`", inline=False)
    return embed


@bot.command(name="hash")
async def hash_cmd(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔐 SHA-256", text, hashlib.sha256(text.encode()).hexdigest(), discord.Color.green()))


@bot.command()
async def sha1(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔐 SHA-1", text, hashlib.sha1(text.encode()).hexdigest(), discord.Color.green()))


@bot.command()
async def sha512(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔐 SHA-512", text, hashlib.sha512(text.encode()).hexdigest(), discord.Color.green()))


@bot.command()
async def md5(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔐 MD5", text, hashlib.md5(text.encode()).hexdigest(), discord.Color.blue()))


@bot.command()
async def crc32(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔐 CRC32", text, format(zlib.crc32(text.encode()) & 0xFFFFFFFF, "08x"), discord.Color.blue()))


@bot.command()
async def fingerprint(ctx, *, text):
    fp = hashlib.sha256(text.encode()).hexdigest()[:16]
    await ctx.send(embed=_hash_embed("🔎 Fingerprint", text, fp, discord.Color.teal()))


@bot.command()
async def encode(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔒 Base64 Encoded", text, base64.b64encode(text.encode()).decode(), discord.Color.blue()))


@bot.command()
async def decode(ctx, *, text):
    try:
        await ctx.send(embed=_hash_embed("🔓 Base64 Decoded", text, base64.b64decode(text.encode()).decode(), discord.Color.blue()))
    except Exception:
        await ctx.send("❌ Invalid Base64 string.")


@bot.command(name="base32")
async def base32_cmd(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔒 Base32 Encoded", text, base64.b32encode(text.encode()).decode(), discord.Color.blue()))


@bot.command()
async def base32decode(ctx, *, text):
    try:
        await ctx.send(embed=_hash_embed("🔓 Base32 Decoded", text, base64.b32decode(text.encode()).decode(), discord.Color.blue()))
    except Exception:
        await ctx.send("❌ Invalid Base32 string.")


@bot.command()
async def hexencode(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔣 Hex Encoded", text, text.encode().hex(), discord.Color.blue()))


@bot.command()
async def hexdecode(ctx, *, text):
    try:
        await ctx.send(embed=_hash_embed("🔣 Hex Decoded", text, bytes.fromhex(text.replace(" ", "")).decode(), discord.Color.blue()))
    except Exception:
        await ctx.send("❌ Invalid hex string.")


@bot.command()
async def binary(ctx, *, text):
    result = " ".join(format(ord(c), "08b") for c in text)
    await ctx.send(embed=_hash_embed("💻 Binary", text, result[:1000], discord.Color.blue()))


@bot.command()
async def unbinary(ctx, *, bits):
    try:
        chars = bits.split()
        result = "".join(chr(int(b, 2)) for b in chars)
        await ctx.send(embed=_hash_embed("💻 From Binary", bits, result, discord.Color.blue()))
    except Exception:
        await ctx.send("❌ Invalid binary (space-separated bytes).")


@bot.command()
async def rot13(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔄 ROT13", text, codecs.encode(text, "rot_13"), discord.Color.blue()))


@bot.command()
async def caesar(ctx, shift: int, *, text):
    def sh(c):
        if c.isupper():
            return chr((ord(c) - 65 + shift) % 26 + 65)
        if c.islower():
            return chr((ord(c) - 97 + shift) % 26 + 97)
        return c
    await ctx.send(embed=_hash_embed(f"🔄 Caesar (+{shift})", text, "".join(sh(c) for c in text), discord.Color.blue()))


@bot.command()
async def atbash(ctx, *, text):
    def ab(c):
        if c.isupper():
            return chr(90 - (ord(c) - 65))
        if c.islower():
            return chr(122 - (ord(c) - 97))
        return c
    await ctx.send(embed=_hash_embed("🔄 Atbash", text, "".join(ab(c) for c in text), discord.Color.blue()))


@bot.command()
async def leet(ctx, *, text):
    table = str.maketrans({"a":"4","e":"3","i":"1","o":"0","s":"5","t":"7","l":"1","g":"9"})
    await ctx.send(embed=_hash_embed("🤖 Leetspeak", text, text.lower().translate(table), discord.Color.blue()))


@bot.command()
async def morse(ctx, *, text):
    result = " ".join(MORSE_CODE.get(c, "?") for c in text.lower())
    await ctx.send(embed=_hash_embed("📡 Morse", text, result[:1000], discord.Color.blue()))


@bot.command()
async def unmorse(ctx, *, code):
    result = "".join(MORSE_REV.get(c, "?") for c in code.split())
    await ctx.send(embed=_hash_embed("📡 From Morse", code, result, discord.Color.blue()))


@bot.command()
async def urlencode(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔗 URL Encoded", text, urllib.parse.quote(text), discord.Color.blue()))


@bot.command()
async def urldecode(ctx, *, text):
    await ctx.send(embed=_hash_embed("🔗 URL Decoded", text, urllib.parse.unquote(text), discord.Color.blue()))


@bot.command()
async def jwtdecode(ctx, *, token):
    try:
        parts = token.split(".")
        if len(parts) < 2:
            raise ValueError
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        decoded = base64.urlsafe_b64decode(payload).decode()
        await ctx.send(embed=_hash_embed("🪪 JWT Payload", token[:40], decoded[:1000], discord.Color.purple()))
    except Exception:
        await ctx.send("❌ Invalid JWT.")


@bot.command()
async def entropy(ctx, *, text):
    if not text:
        await ctx.send("❌ Provide text.")
        return
    counts = Counter(text)
    ent = -sum((c/len(text)) * _math.log2(c/len(text)) for c in counts.values())
    await ctx.send(f"📊 Shannon entropy: **{ent:.3f}** bits/char ({ent*len(text):.1f} total).")


@bot.command()
async def luhn(ctx, *, number):
    digits = [int(d) for d in number if d.isdigit()]
    if not digits:
        await ctx.send("❌ No digits found.")
        return
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    valid = total % 10 == 0
    await ctx.send(f"{'✅ Valid' if valid else '❌ Invalid'} Luhn checksum (sum={total}).")


@bot.command()
async def validemail(ctx, *, text):
    ok = bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", text.strip()))
    await ctx.send(f"{'✅' if ok else '❌'} `{text}` is {'a valid' if ok else 'not a valid'} email.")


@bot.command()
async def validurl(ctx, *, text):
    ok = bool(re.match(r"^https?://[^\s]+\.[^\s]+$", text.strip()))
    await ctx.send(f"{'✅' if ok else '❌'} `{text}` is {'a valid' if ok else 'not a valid'} URL.")


@bot.command()
async def uuidgen(ctx):
    await ctx.send(f"🆔 `{uuid.uuid4()}`")


@bot.command()
async def token(ctx, length: int = 32):
    length = max(4, min(length, 128))
    await ctx.send(f"🔑 `{secrets.token_hex(length // 2)}`")


@bot.command()
async def genpin(ctx, length: int = 4):
    length = max(3, min(length, 12))
    await ctx.send(f"🔢 PIN: `{''.join(secrets.choice('0123456789') for _ in range(length))}`")


@bot.command()
async def randstr(ctx, length: int = 16):
    length = max(1, min(length, 200))
    chars = _string.ascii_letters + _string.digits
    await ctx.send(f"🔤 `{''.join(secrets.choice(chars) for _ in range(length))}`")


@bot.command()
async def passphrase(ctx, words: int = 4):
    words = max(2, min(words, 10))
    wl = ["river","stone","cloud","ember","frost","maple","quartz","raven","willow","cobalt",
          "harbor","meadow","cipher","photon","tundra","saffron","velvet","onyx","zephyr","cedar"]
    phrase = "-".join(secrets.choice(wl) for _ in range(words))
    await ctx.send(f"🔐 `{phrase}`")


@bot.command()
async def randmac(ctx):
    mac = ":".join(format(secrets.randbelow(256), "02x") for _ in range(6))
    await ctx.send(f"🖧 `{mac}`")


@bot.command()
async def maskip(ctx, ip: str):
    parts = ip.split(".")
    if len(parts) == 4:
        await ctx.send(f"🛡️ `{parts[0]}.{parts[1]}.{parts[2]}.xxx`")
    else:
        await ctx.send("❌ Provide an IPv4 address.")


@bot.command()
async def nslookup(ctx, domain: str):
    try:
        ip = socket.gethostbyname(domain)
        await ctx.send(f"🌐 `{domain}` → `{ip}`")
    except Exception:
        await ctx.send("❌ Could not resolve domain.")


@bot.command()
async def portinfo(ctx, port: int):
    ports = {20:"FTP data",21:"FTP",22:"SSH",23:"Telnet",25:"SMTP",53:"DNS",80:"HTTP",
             110:"POP3",143:"IMAP",443:"HTTPS",3306:"MySQL",3389:"RDP",5432:"PostgreSQL",
             6379:"Redis",8080:"HTTP-alt",27017:"MongoDB"}
    await ctx.send(f"🔌 Port **{port}**: {ports.get(port, 'No well-known service')}")


@bot.command()
async def useragent(ctx):
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148",
    ]
    await ctx.send(f"🕵️ `{random.choice(uas)}`")


@bot.command()
async def pwcheck(ctx, *, password):
    score = 0
    tips = []
    if len(password) >= 8: score += 1
    else: tips.append("• At least 8 characters")
    if len(password) >= 12: score += 1
    if re.search(r'[A-Z]', password): score += 1
    else: tips.append("• Add uppercase letters")
    if re.search(r'[a-z]', password): score += 1
    else: tips.append("• Add lowercase letters")
    if re.search(r'\d', password): score += 1
    else: tips.append("• Add numbers")
    if re.search(r'[!@#$%^&*(),.?\":{}|<>]', password): score += 1
    else: tips.append("• Add special characters")
    labels = ["Very Weak","Weak","Fair","Good","Strong","Very Strong"]
    colors = [discord.Color.red(),discord.Color.red(),discord.Color.orange(),discord.Color.yellow(),discord.Color.green(),discord.Color.green()]
    embed = discord.Embed(title="🔑 Password Strength", color=colors[min(score,5)])
    embed.add_field(name="Strength", value=f"**{labels[min(score,5)]}** ({score}/6)", inline=False)
    if tips:
        embed.add_field(name="Suggestions", value="\n".join(tips), inline=False)
    await ctx.send(embed=embed)
    await ctx.message.delete()


@bot.command()
async def pwgen(ctx, length: int = 16):
    if not 8 <= length <= 64:
        await ctx.send("❌ Length must be 8-64.")
        return
    chars = _string.ascii_letters + _string.digits + "!@#$%^&*()"
    pw = "".join(secrets.choice(chars) for _ in range(length))
    try:
        await ctx.author.send(f"🔑 Generated password (`{length}` chars):\n```\n{pw}\n```")
        await ctx.send("✅ Password sent to your DMs!")
    except Exception:
        await ctx.send("❌ Enable DMs from server members first.")


@bot.command()
async def permissions(ctx, member: discord.Member = None):
    member = member or ctx.author
    perms = [p.replace("_", " ").title() for p, v in member.guild_permissions if v]
    embed = discord.Embed(title=f"🛡️ Permissions — {member}", description="\n".join(f"✅ {p}" for p in perms) or "None", color=discord.Color.blue())
    await ctx.send(embed=embed)


@bot.command()
async def serverinfo(ctx):
    g = ctx.guild
    embed = discord.Embed(title=f"📊 {g.name}", color=discord.Color.blurple(), timestamp=datetime.datetime.utcnow())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Owner", value=str(g.owner))
    embed.add_field(name="Members", value=str(g.member_count))
    embed.add_field(name="Channels", value=str(len(g.channels)))
    embed.add_field(name="Roles", value=str(len(g.roles)))
    embed.add_field(name="Boosts", value=str(g.premium_subscription_count))
    embed.add_field(name="Verification", value=str(g.verification_level))
    embed.add_field(name="Created", value=g.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="ID", value=str(g.id))
    embed.add_field(name="Emojis", value=str(len(g.emojis)))
    await ctx.send(embed=embed)


@bot.command()
async def userinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    roles = [r.mention for r in member.roles[1:]]
    embed = discord.Embed(title=f"👤 {member}", color=member.color, timestamp=datetime.datetime.utcnow())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=str(member.id))
    embed.add_field(name="Nickname", value=member.nick or "None")
    embed.add_field(name="Status", value=str(member.status))
    embed.add_field(name="Joined", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "Unknown")
    embed.add_field(name="Created", value=member.created_at.strftime("%Y-%m-%d"))
    embed.add_field(name="Bot", value="Yes" if member.bot else "No")
    embed.add_field(name="Top Role", value=member.top_role.mention)
    embed.add_field(name="Roles", value=" ".join(roles[:8]) or "None", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def roleinfo(ctx, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    embed = discord.Embed(title=f"🎭 {role.name}", color=role.color)
    embed.add_field(name="ID", value=str(role.id))
    embed.add_field(name="Color", value=str(role.color))
    embed.add_field(name="Members", value=str(len(role.members)))
    embed.add_field(name="Mentionable", value=str(role.mentionable))
    embed.add_field(name="Hoisted", value=str(role.hoist))
    embed.add_field(name="Position", value=str(role.position))
    await ctx.send(embed=embed)


@bot.command()
async def channelinfo(ctx, channel: discord.TextChannel = None):
    ch = channel or ctx.channel
    embed = discord.Embed(title=f"📝 #{ch.name}", color=discord.Color.blue())
    embed.add_field(name="ID", value=str(ch.id))
    embed.add_field(name="Category", value=str(ch.category) if ch.category else "None")
    embed.add_field(name="Topic", value=ch.topic or "None", inline=False)
    embed.add_field(name="Slowmode", value=f"{ch.slowmode_delay}s")
    embed.add_field(name="NSFW", value=str(ch.nsfw))
    embed.add_field(name="Created", value=ch.created_at.strftime("%Y-%m-%d"))
    await ctx.send(embed=embed)


@bot.command()
async def botinfo(ctx):
    delta = datetime.datetime.utcnow() - BOT_START
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    embed = discord.Embed(title="🤖 Em-Bot Info", color=discord.Color.blurple())
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.add_field(name="Name", value=str(bot.user))
    embed.add_field(name="ID", value=str(bot.user.id))
    embed.add_field(name="Servers", value=str(len(bot.guilds)))
    embed.add_field(name="Commands", value=str(len(bot.commands)))
    embed.add_field(name="Uptime", value=f"{h}h {m}m {s}s")
    embed.add_field(name="Prefix", value=".")
    await ctx.send(embed=embed)


@bot.command()
async def ipinfo(ctx, ip: str):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"http://ip-api.com/json/{ip}") as resp:
                data = await resp.json()
            if data["status"] == "success":
                embed = discord.Embed(title=f"🌐 IP: {ip}", color=discord.Color.blue())
                embed.add_field(name="Country", value=data.get("country", "N/A"))
                embed.add_field(name="Region", value=data.get("regionName", "N/A"))
                embed.add_field(name="City", value=data.get("city", "N/A"))
                embed.add_field(name="ISP", value=data.get("isp", "N/A"))
                embed.add_field(name="Timezone", value=data.get("timezone", "N/A"))
                embed.add_field(name="Org", value=data.get("org", "N/A"))
                await ctx.send(embed=embed)
            else:
                await ctx.send("❌ Invalid or private IP.")
        except Exception:
            await ctx.send("❌ Could not fetch IP info.")


@bot.command()
async def inviteinfo(ctx, code: str):
    try:
        invite = await bot.fetch_invite(code)
        embed = discord.Embed(title="📨 Invite Info", color=discord.Color.blue())
        embed.add_field(name="Server", value=invite.guild.name if invite.guild else "N/A")
        embed.add_field(name="Channel", value=str(invite.channel) if invite.channel else "N/A")
        embed.add_field(name="Inviter", value=str(invite.inviter) if invite.inviter else "N/A")
        embed.add_field(name="Uses", value=str(invite.uses) if invite.uses is not None else "N/A")
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ Invalid invite code.")


# ── FUN ────────────────────────────────────────────────────────────────────────
@bot.command(name="8ball")
async def eightball(ctx, *, question):
    responses = ["🟢 It is certain.","🟢 Definitely so.","🟢 Without a doubt.","🟢 Yes!","🟢 As I see it, yes.",
                 "🟡 Reply hazy...","🟡 Ask again later.","🟡 Cannot predict now.","🔴 Don't count on it.",
                 "🔴 My reply is no.","🔴 Very doubtful.","🔴 Outlook not so good."]
    embed = discord.Embed(title="🎱 Magic 8-Ball", color=discord.Color.purple())
    embed.add_field(name="Question", value=question, inline=False)
    embed.add_field(name="Answer", value=random.choice(responses), inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def roll(ctx, dice: str = "1d6"):
    try:
        n, s = map(int, dice.lower().split("d"))
        if not (1 <= n <= 20 and 2 <= s <= 100):
            raise ValueError
        rolls = [random.randint(1, s) for _ in range(n)]
        embed = discord.Embed(title="🎲 Dice Roll", color=discord.Color.green())
        embed.add_field(name="Dice", value=f"`{dice}`")
        embed.add_field(name="Rolls", value=", ".join(map(str, rolls)))
        embed.add_field(name="Total", value=str(sum(rolls)))
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ Format: `.roll 2d6` (1-20 dice, 2-100 sides)")


@bot.command()
async def coinflip(ctx):
    await ctx.send(f"{ctx.author.mention} flipped: **{random.choice(['Heads 🪙','Tails 🪙'])}**!")


@bot.command()
async def rps(ctx, choice: str):
    choices = ["rock", "paper", "scissors"]
    if choice.lower() not in choices:
        await ctx.send("❌ Choose `rock`, `paper`, or `scissors`.")
        return
    bc = random.choice(choices)
    emojis = {"rock":"🪨","paper":"📄","scissors":"✂️"}
    wins = {"rock":"scissors","paper":"rock","scissors":"paper"}
    if choice.lower() == bc:
        result = "🤝 Tie!"
    elif wins[choice.lower()] == bc:
        result = "🎉 You win!"
    else:
        result = "😔 I win!"
    embed = discord.Embed(title="✂️ Rock Paper Scissors", color=discord.Color.blurple())
    embed.add_field(name="You", value=f"{emojis[choice.lower()]} {choice.capitalize()}")
    embed.add_field(name="Me", value=f"{emojis[bc]} {bc.capitalize()}")
    embed.add_field(name="Result", value=result, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def joke(ctx):
    jokes = [("Why don't scientists trust atoms?","Because they make up everything!"),
             ("Why did the scarecrow win an award?","He was outstanding in his field!"),
             ("What do you call a fake noodle?","An impasta!"),
             ("I'm reading a book about anti-gravity.","It's impossible to put down!"),
             ("Why was the math book sad?","Too many problems."),
             ("What do you call cheese that isn't yours?","Nacho cheese!"),
             ("Why can't you give Elsa a balloon?","She'll let it go."),
             ("Why did the bicycle fall over?","It was two-tired."),
             ("What do you call a sleeping dinosaur?","A dino-snore!")]
    setup, punchline = random.choice(jokes)
    embed = discord.Embed(title="😂 Joke", color=discord.Color.yellow())
    embed.add_field(name="Setup", value=setup, inline=False)
    embed.add_field(name="Punchline", value=punchline, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def roast(ctx, member: discord.Member):
    roasts = ["is so slow, a turtle laps them.","has the personality of a wet paper bag.",
              "is proof evolution can reverse.","could mess up a one-car funeral.",
              "is the reason shampoo bottles have instructions.","is the human version of a participation trophy.",
              "brings so little to the table, they have no seat.","has the charisma of a blank Word document."]
    await ctx.send(f"🔥 **{member.display_name}** {random.choice(roasts)}")


@bot.command()
async def compliment(ctx, member: discord.Member):
    comps = ["lights up every room! ✨","is genuinely one of the kindest people here. 💙",
             "has an amazing sense of humor! 😄","makes this server better just by being here. 🌟",
             "is incredibly talented. 🎨","has a heart of gold. 💛","has infectious positive energy. ⚡",
             "is smarter than they think. 🧠","would make an excellent best friend. 🤝"]
    await ctx.send(f"💝 **{member.display_name}** {random.choice(comps)}")


@bot.command()
async def pickup(ctx, member: discord.Member = None):
    target = member.display_name if member else "you"
    lines = [f"Are you a magician, {target}? Because whenever I look at you, everyone else disappears.",
             f"Hey {target}, do you have a map? I keep getting lost in your eyes.",
             f"{target}, are you Wi-Fi? Because I'm feeling a connection.",
             f"Is your name Google, {target}? Because you're everything I've been searching for.",
             f"{target}, are you a parking ticket? Because you've got 'fine' written all over you."]
    await ctx.send(f"💬 {random.choice(lines)}")


@bot.command()
async def ship(ctx, member1: discord.Member, member2: discord.Member):
    score = random.randint(0, 100)
    status = "💔 Not a match..." if score < 30 else "💛 Some potential!" if score < 60 else "💕 Compatible!" if score < 80 else "❤️ Perfect match!"
    bar = "█" * (score // 10) + "░" * (10 - score // 10)
    embed = discord.Embed(title="💘 Compatibility", color=discord.Color.pink())
    embed.add_field(name="Couple", value=f"{member1.display_name} & {member2.display_name}", inline=False)
    embed.add_field(name="Score", value=f"{score}% `{bar}`", inline=False)
    embed.add_field(name="Verdict", value=status, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def marry(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't marry yourself!")
        return
    if random.random() > 0.4:
        await ctx.send(f"💍 {member.mention} said **YES** to {ctx.author.mention}! 🎉 Congratulations! 💕")
    else:
        await ctx.send(f"💔 {member.mention} said **no** to {ctx.author.mention}... better luck next time.")


@bot.command()
async def rate(ctx, *, thing):
    await ctx.send(f"⭐ I rate **{thing}** a **{random.randint(0,10)}/10**!")


@bot.command()
async def chance(ctx, *, thing):
    await ctx.send(f"🔮 There's a **{random.randint(0,100)}%** chance of **{thing}**.")


@bot.command()
async def yesno(ctx, *, question):
    await ctx.send(f"🤔 **{random.choice(['Yes ✅','No ❌','Maybe 🤷','Absolutely 💯','Definitely not 🚫'])}**")


@bot.command()
async def reverse(ctx, *, text):
    await ctx.send(f"🔄 {text[::-1]}")


@bot.command()
async def mock(ctx, *, text):
    await ctx.send("🤡 " + "".join(c.upper() if i % 2 == 0 else c.lower() for i, c in enumerate(text)))


@bot.command()
async def clap(ctx, *, text):
    await ctx.send("👏 " + " 👏 ".join(text.split()) + " 👏")


@bot.command()
async def owoify(ctx, *, text):
    result = text.replace("r", "w").replace("l", "w").replace("R", "W").replace("L", "W")
    result = re.sub(r"n([aeiou])", r"ny\1", result)
    await ctx.send(f"🥺 {result} owo")


@bot.command()
async def emojify(ctx, *, text):
    out = ""
    for c in text.lower():
        if c.isalpha():
            out += chr(0x1F1E6 + (ord(c) - 97)) + " "
        elif c == " ":
            out += "   "
        else:
            out += c
    await ctx.send(out[:1000] or "❌ Nothing to emojify.")


@bot.command()
async def vaporwave(ctx, *, text):
    out = "".join(chr(ord(c) + 0xFEE0) if 33 <= ord(c) <= 126 else c for c in text)
    await ctx.send(out[:1000])


@bot.command()
async def ascii(ctx, *, text):
    if len(text) > 10:
        await ctx.send("❌ Max 10 characters.")
        return
    await ctx.send(f"```\n{'  '.join(list(text.upper()))}\n```")


@bot.command()
async def trivia(ctx):
    questions = [("Capital of France?","paris"),("Sides of a hexagon?","6"),("Largest planet?","jupiter"),
                 ("WWII end year?","1945"),("Chemical symbol for water?","h2o"),("Who wrote Romeo and Juliet?","shakespeare"),
                 ("Fastest land animal?","cheetah"),("Number of continents?","7"),("Square root of 144?","12"),
                 ("Smallest country?","vatican"),("Human bones count?","206"),("Boiling point of water in Celsius?","100")]
    q, a = random.choice(questions)
    embed = discord.Embed(title="🧠 Trivia!", description=q, color=discord.Color.purple())
    embed.set_footer(text="15 seconds to answer!")
    await ctx.send(embed=embed)
    def check(m):
        return m.channel == ctx.channel and not m.author.bot
    try:
        msg = await bot.wait_for("message", check=check, timeout=15.0)
        if msg.content.lower().strip() == a:
            xp_data[msg.author.id] += 50
            await ctx.send(f"🎉 {msg.author.mention} got it! Answer: **{a}**! (+50 XP)")
        else:
            await ctx.send(f"❌ Wrong! Answer: **{a}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! Answer: **{a}**.")


@bot.command()
async def scramble(ctx):
    words = ["python","discord","server","coding","gaming","keyboard","monitor","internet","programming","developer"]
    word = random.choice(words)
    scrambled = "".join(random.sample(word, len(word)))
    await ctx.send(f"🔀 Unscramble this word: **`{scrambled}`**\n*You have 20 seconds!*")
    def check(m):
        return m.channel == ctx.channel and not m.author.bot
    try:
        msg = await bot.wait_for("message", check=check, timeout=20.0)
        if msg.content.lower().strip() == word:
            xp_data[msg.author.id] += 30
            await ctx.send(f"🎉 {msg.author.mention} got it! The word was **{word}**! (+30 XP)")
        else:
            await ctx.send(f"❌ Wrong! The word was **{word}**.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! The word was **{word}**.")


@bot.command()
async def guessnum(ctx):
    target = random.randint(1, 20)
    await ctx.send("🔢 I'm thinking of a number **1-20**. You have 15 seconds and one guess!")
    def check(m):
        return m.channel == ctx.channel and not m.author.bot and m.content.isdigit()
    try:
        msg = await bot.wait_for("message", check=check, timeout=15.0)
        guess = int(msg.content)
        if guess == target:
            xp_data[msg.author.id] += 20
            await ctx.send(f"🎉 {msg.author.mention} nailed it! It was **{target}**! (+20 XP)")
        else:
            await ctx.send(f"❌ It was **{target}**. {msg.author.mention} guessed {guess}.")
    except asyncio.TimeoutError:
        await ctx.send(f"⏰ Time's up! It was **{target}**.")


@bot.command()
async def enlarge(ctx, emoji: str):
    if emoji.startswith("<") and ":" in emoji:
        eid = emoji.split(":")[-1].rstrip(">")
        ext = "gif" if emoji.startswith("<a") else "png"
        embed = discord.Embed(title="🔍 Enlarged Emoji", color=discord.Color.blurple())
        embed.set_image(url=f"https://cdn.discordapp.com/emojis/{eid}.{ext}")
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ Provide a custom server emoji.")


def _action(verb, emoji):
    async def cmd(ctx, member: discord.Member = None):
        if member is None:
            await ctx.send(f"❌ Mention someone to {verb}!")
            return
        if member.id == ctx.author.id:
            await ctx.send(f"{emoji} {ctx.author.mention} {verb}s themselves... okay then.")
            return
        await ctx.send(f"{emoji} {ctx.author.mention} {verb}s {member.mention}!")
    return cmd


hug       = bot.command(name="hug")(_action("hug", "🤗"))
slap      = bot.command(name="slap")(_action("slap", "👋"))
punch     = bot.command(name="punch")(_action("punch", "👊"))
kiss      = bot.command(name="kiss")(_action("kiss", "💋"))
pat       = bot.command(name="pat")(_action("pat", "🫳"))
highfive  = bot.command(name="highfive")(_action("high-five", "🙌"))
bonk      = bot.command(name="bonk")(_action("bonk", "🔨"))
cookie    = bot.command(name="cookie")(_action("give a cookie to", "🍪"))
kill      = bot.command(name="kill")(_action("dramatically defeats", "⚔️"))


def _rating(label, emoji):
    async def cmd(ctx, member: discord.Member = None):
        member = member or ctx.author
        score = random.randint(0, 100)
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        await ctx.send(f"{emoji} **{member.display_name}** is **{score}% {label}** today!\n`{bar}`")
    return cmd


howedgy  = bot.command(name="howedgy")(_rating("edgy", "🗡️"))
howcool  = bot.command(name="howcool")(_rating("cool", "😎"))
howrich  = bot.command(name="howrich")(_rating("rich", "🤑"))
howlucky = bot.command(name="howlucky")(_rating("lucky", "🍀"))
howhot   = bot.command(name="howhot")(_rating("hot", "🔥"))
howfunny = bot.command(name="howfunny")(_rating("funny", "😂"))
howgay   = bot.command(name="howgay")(_rating("gay", "🌈"))
howcringe = bot.command(name="howcringe")(_rating("cringe", "😬"))
howbased = bot.command(name="howbased")(_rating("based", "😤"))
simp     = bot.command(name="simp")(_rating("simp", "💘"))
sus      = bot.command(name="sus")(_rating("sus", "📮"))


@bot.command()
async def pp(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"📏 **{member.display_name}**'s pp:\n`8{'=' * random.randint(0, 15)}D`")


@bot.command()
async def iq(ctx, member: discord.Member = None):
    member = member or ctx.author
    score = random.randint(1, 200)
    label = "🧠 Genius!" if score > 140 else "😊 Smart!" if score > 110 else "😐 Average" if score > 85 else "😬 Uh oh..."
    await ctx.send(f"🧠 **{member.display_name}** has an IQ of **{score}** — {label}")


@bot.command()
async def vibe(ctx, member: discord.Member = None):
    member = member or ctx.author
    vibes = ["immaculate ✨","chaotic 🌀","mysterious 🌑","energetic ⚡","chill 😎","wholesome 🥰","unhinged 😵","based 😤","cozy 🍵","electric 🔥"]
    await ctx.send(f"🌊 **{member.display_name}**'s vibe today is: **{random.choice(vibes)}**")


@bot.command()
async def fortune(ctx):
    fortunes = ["A surprise is waiting for you around the corner. 🎁","Your hard work will soon pay off. 💪",
                "Today is a great day to start something new. 🌱","Trust your instincts. 🔮","The best is yet to come. ✨",
                "Help someone today and it will come back to you. 🤝","An exciting opportunity is on the horizon. 🌅",
                "Focus and success will follow. 🎯","Small steps lead to big changes. 🚀"]
    await ctx.send(f"🥠 **Fortune Cookie:** {random.choice(fortunes)}")


@bot.command()
async def fact(ctx):
    facts = ["Honey never spoils.","Octopuses have three hearts.","Bananas are berries, but strawberries aren't.",
             "A group of flamingos is called a 'flamboyance'.","Sharks existed before trees.",
             "The Eiffel Tower can grow taller in summer.","Wombat poop is cube-shaped.",
             "There are more stars in the universe than grains of sand on Earth."]
    await ctx.send(f"💡 **Fact:** {random.choice(facts)}")


@bot.command()
async def catfact(ctx):
    facts = ["Cats sleep 13-16 hours a day.","A cat can't taste sweetness.","Cats have five toes on front paws but four on the back.",
             "A group of cats is called a 'clowder'.","Cats can rotate their ears 180 degrees.","A cat's nose print is unique."]
    await ctx.send(f"🐱 **Cat Fact:** {random.choice(facts)}")


@bot.command()
async def quote(ctx):
    quotes = ["The only way to do great work is to love what you do.","Stay hungry, stay foolish.",
              "Whether you think you can or you can't, you're right.","Dream big and dare to fail.",
              "Action is the foundational key to all success.","The best time to start was yesterday; the next best is now."]
    await ctx.send(f"📜 *{random.choice(quotes)}*")


@bot.command()
async def advice(ctx):
    advices = ["Drink more water.","Take breaks — they make you more productive.","Be kind; everyone is fighting a hard battle.",
               "Save a little money every month.","Sleep is not optional.","Comparison is the thief of joy.",
               "Done is better than perfect."]
    await ctx.send(f"🧭 **Advice:** {random.choice(advices)}")


@bot.command()
async def excuse(ctx):
    excuses = ["My internet went down.","I was stuck in traffic.","My alarm didn't go off.","The dog ate my homework.",
               "I had a sudden migraine.","My phone died.","I lost track of time.","There was a family emergency."]
    await ctx.send(f"🤥 **Excuse:** {random.choice(excuses)}")


@bot.command()
async def wouldyourather(ctx):
    questions = ["Fight 100 duck-sized horses OR 1 horse-sized duck?","Never use a phone again OR never watch TV again?",
                 "Always be 10 minutes late OR always 20 minutes early?","Be able to fly OR be invisible?",
                 "Speak all languages OR play every instrument?","Live in the past OR the future?","Have no internet OR no music?"]
    await ctx.send(f"🤔 **Would You Rather:**\n{random.choice(questions)}")


@bot.command()
async def neverhaveiever(ctx):
    statements = ["Never have I ever stayed up past 3 AM.","Never have I ever eaten an entire pizza alone.",
                  "Never have I ever cried at a movie.","Never have I ever sent a text to the wrong person.",
                  "Never have I ever fallen asleep in class.","Never have I ever binge-watched a series in one day."]
    await ctx.send(f"🙋 **Never Have I Ever:**\n{random.choice(statements)}")


@bot.command()
async def thisorthat(ctx):
    pairs = [("Coffee ☕","Tea 🍵"),("Dogs 🐶","Cats 🐱"),("Pizza 🍕","Burgers 🍔"),("Morning 🌅","Night 🌙"),
             ("Beach 🏖️","Mountains ⛰️"),("Netflix","YouTube"),("Texting 💬","Calling 📞"),("Summer ☀️","Winter ❄️")]
    a, b = random.choice(pairs)
    embed = discord.Embed(title="⚡ This or That?", color=discord.Color.purple())
    embed.add_field(name="Option A", value=a)
    embed.add_field(name="Option B", value=b)
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🅰️")
    await msg.add_reaction("🅱️")


@bot.command()
async def truth(ctx):
    truths = ["What's the most embarrassing thing you've done online?","What's your biggest fear?",
              "Have you ever lied to get out of plans?","What's the worst gift you've ever received?",
              "What's a secret talent you have?","What's the most childish thing you still do?"]
    await ctx.send(f"🤫 **Truth:** {random.choice(truths)}")


@bot.command()
async def dare(ctx):
    dares = ["Change your nickname to 'Bot Slave' for 10 minutes.","Say something nice to the last person who messaged.",
             "Write a 2-sentence poem about the server.","Speak in rhymes for the next 5 minutes.",
             "Describe yourself in 3 words right now.","Type with your elbows for your next 2 messages."]
    await ctx.send(f"😈 **Dare:** {random.choice(dares)}")


# ── UTILITY ────────────────────────────────────────────────────────────────────
@bot.command()
async def afk(ctx, *, reason="AFK"):
    afk_data[ctx.author.id] = (reason, datetime.datetime.utcnow())
    await ctx.send(f"💤 **{ctx.author.display_name}** is now AFK: {reason}")


@bot.command()
async def remind(ctx, minutes: int, *, message):
    reminder_data.append({"user_id": ctx.author.id, "channel_id": ctx.channel.id,
                          "time": datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes), "message": message})
    await ctx.send(f"⏰ Reminder set for **{minutes}** minute(s): {message}")


@bot.command()
async def snipe(ctx):
    msg = snipe_data.get(ctx.channel.id)
    if not msg:
        await ctx.send("❌ Nothing to snipe!")
        return
    embed = discord.Embed(description=msg.content or "*No text*", color=discord.Color.red(), timestamp=msg.created_at)
    embed.set_author(name=str(msg.author), icon_url=msg.author.display_avatar.url)
    embed.set_footer(text="Deleted message")
    await ctx.send(embed=embed)


@bot.command()
async def editsnipe(ctx):
    data = edit_snipe_data.get(ctx.channel.id)
    if not data:
        await ctx.send("❌ Nothing to edit-snipe!")
        return
    before, after = data
    embed = discord.Embed(title="✏️ Edit Snipe", color=discord.Color.orange())
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    embed.add_field(name="Before", value=before.content or "*empty*", inline=False)
    embed.add_field(name="After", value=after.content or "*empty*", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def poll(ctx, *, text):
    parts = [p.strip() for p in text.split("|")]
    if len(parts) < 3:
        await ctx.send("❌ Format: `.poll Question | Opt1 | Opt2`")
        return
    q, options = parts[0], parts[1:]
    if len(options) > 9:
        await ctx.send("❌ Max 9 options.")
        return
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣"]
    desc = "\n".join(f"{emojis[i]} {opt}" for i, opt in enumerate(options))
    embed = discord.Embed(title=f"📊 {q}", description=desc, color=discord.Color.blurple())
    embed.set_footer(text=f"Poll by {ctx.author}")
    msg = await ctx.send(embed=embed)
    for i in range(len(options)):
        await msg.add_reaction(emojis[i])


@bot.command()
async def quickpoll(ctx, *, question):
    embed = discord.Embed(title="📊 Quick Poll", description=question, color=discord.Color.blurple())
    embed.set_footer(text=f"Poll by {ctx.author}")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("👍")
    await msg.add_reaction("👎")


@bot.command()
async def note(ctx, *, text):
    notes_data[ctx.author.id].append(text)
    await ctx.send(f"📝 Note #{len(notes_data[ctx.author.id])} saved!")


@bot.command()
async def notes(ctx):
    user_notes = notes_data.get(ctx.author.id, [])
    if not user_notes:
        await ctx.send("📭 No notes saved.")
        return
    embed = discord.Embed(title="📝 Your Notes", color=discord.Color.blue())
    for i, n in enumerate(user_notes, 1):
        embed.add_field(name=f"#{i}", value=n, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def deletenote(ctx, number: int):
    user_notes = notes_data.get(ctx.author.id, [])
    if not user_notes or not 1 <= number <= len(user_notes):
        await ctx.send("❌ Invalid note number.")
        return
    removed = notes_data[ctx.author.id].pop(number - 1)
    await ctx.send(f"🗑️ Deleted note #{number}: {removed[:50]}")


@bot.command()
async def clearnotes(ctx):
    notes_data[ctx.author.id] = []
    await ctx.send("🗑️ All notes cleared.")


@bot.command()
async def todo(ctx, *, text):
    todo_data[ctx.author.id].append({"text": text, "done": False})
    await ctx.send(f"✅ To-do #{len(todo_data[ctx.author.id])} added!")


@bot.command()
async def todos(ctx):
    items = todo_data.get(ctx.author.id, [])
    if not items:
        await ctx.send("📭 No to-dos.")
        return
    embed = discord.Embed(title="📋 Your To-Dos", color=discord.Color.green())
    for i, item in enumerate(items, 1):
        embed.add_field(name=f"{'✅' if item['done'] else '⬜'} #{i}", value=item["text"], inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def donetodo(ctx, number: int):
    items = todo_data.get(ctx.author.id, [])
    if not items or not 1 <= number <= len(items):
        await ctx.send("❌ Invalid to-do number.")
        return
    todo_data[ctx.author.id][number - 1]["done"] = True
    await ctx.send(f"✅ Marked to-do #{number} as done!")


@bot.command()
async def avatar(ctx, member: discord.Member = None):
    member = member or ctx.author
    embed = discord.Embed(title=f"🖼️ {member.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=member.display_avatar.url)
    await ctx.send(embed=embed)


@bot.command()
async def banner(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    if user.banner:
        embed = discord.Embed(title=f"🖼️ {member.display_name}'s Banner", color=discord.Color.blurple())
        embed.set_image(url=user.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send(f"❌ **{member.display_name}** has no banner.")


@bot.command()
async def ping(ctx):
    latency = round(bot.latency * 1000)
    color = discord.Color.green() if latency < 100 else discord.Color.yellow() if latency < 200 else discord.Color.red()
    embed = discord.Embed(title="🏓 Pong!", color=color)
    embed.add_field(name="Latency", value=f"`{latency}ms`")
    await ctx.send(embed=embed)


@bot.command()
async def uptime(ctx):
    delta = datetime.datetime.utcnow() - BOT_START
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    await ctx.send(embed=discord.Embed(title="⏱️ Uptime", description=f"`{h}h {m}m {s}s`", color=discord.Color.green()))


@bot.command()
async def timestamp(ctx):
    now = datetime.datetime.utcnow()
    embed = discord.Embed(title="🕐 UTC Time", color=discord.Color.blue())
    embed.add_field(name="Date", value=now.strftime("%Y-%m-%d"))
    embed.add_field(name="Time", value=now.strftime("%H:%M:%S"))
    embed.add_field(name="Unix", value=str(int(now.timestamp())))
    await ctx.send(embed=embed)


@bot.command(name="math")
async def math_cmd(ctx, *, expression):
    try:
        expr = expression.replace("^", "**")
        allowed_chars = set("0123456789+-*/.() ")
        clean = expr.replace("**", "")
        if any(c not in allowed_chars for c in clean):
            raise ValueError("Invalid characters")
        result = eval(expr, {"__builtins__": {}}, {"abs": abs, "round": round, "min": min, "max": max})
        embed = discord.Embed(title="🔢 Math", color=discord.Color.green())
        embed.add_field(name="Expression", value=f"`{expression}`", inline=False)
        embed.add_field(name="Result", value=f"`{result}`", inline=False)
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ Invalid expression.")


@bot.command()
async def calculator(ctx, *, expression):
    await math_cmd(ctx, expression=expression)


@bot.command()
async def wordcount(ctx, *, text):
    await ctx.send(f"🔤 **{len(text.split())}** words, **{len(text)}** characters.")


@bot.command()
async def charcount(ctx, *, text):
    await ctx.send(f"🔡 **{len(text)}** characters (**{len(text.replace(' ', ''))}** without spaces).")


@bot.command()
async def upper(ctx, *, text):
    await ctx.send(text.upper()[:2000])


@bot.command()
async def lower(ctx, *, text):
    await ctx.send(text.lower()[:2000])


@bot.command()
async def titlecase(ctx, *, text):
    await ctx.send(text.title()[:2000])


@bot.command()
async def repeat(ctx, times: int, *, text):
    times = max(1, min(times, 20))
    out = (text + " ") * times
    await ctx.send(out[:2000])


@bot.command()
async def randomnumber(ctx, low: int, high: int):
    if low > high:
        low, high = high, low
    await ctx.send(f"🎲 Random number between {low} and {high}: **{random.randint(low, high)}**")


@bot.command()
async def roman(ctx, number: int):
    if not 1 <= number <= 3999:
        await ctx.send("❌ Number must be 1-3999.")
        return
    vals = [(1000,"M"),(900,"CM"),(500,"D"),(400,"CD"),(100,"C"),(90,"XC"),(50,"L"),(40,"XL"),(10,"X"),(9,"IX"),(5,"V"),(4,"IV"),(1,"I")]
    res = ""
    for v, sym in vals:
        while number >= v:
            res += sym
            number -= v
    await ctx.send(f"🏛️ **{res}**")


@bot.command()
async def unroman(ctx, roman: str):
    vals = {"I":1,"V":5,"X":10,"L":50,"C":100,"D":500,"M":1000}
    roman = roman.upper()
    try:
        total, prev = 0, 0
        for c in reversed(roman):
            v = vals[c]
            total += -v if v < prev else v
            prev = max(prev, v)
        await ctx.send(f"🔢 **{total}**")
    except Exception:
        await ctx.send("❌ Invalid Roman numeral.")


@bot.command()
async def tobinary(ctx, number: int):
    await ctx.send(f"💻 `{bin(number)[2:] if number >= 0 else '-' + bin(number)[3:]}`")


@bot.command()
async def tohex(ctx, number: int):
    await ctx.send(f"🔣 `{hex(number)}`")


@bot.command()
async def tooct(ctx, number: int):
    await ctx.send(f"🔢 `{oct(number)}`")


@bot.command()
async def factorial(ctx, n: int):
    if not 0 <= n <= 170:
        await ctx.send("❌ n must be 0-170.")
        return
    await ctx.send(f"❗ {n}! = **{_math.factorial(n)}**")


@bot.command()
async def fibonacci(ctx, n: int):
    if not 1 <= n <= 90:
        await ctx.send("❌ n must be 1-90.")
        return
    a, b = 0, 1
    for _ in range(n - 1):
        a, b = b, a + b
    await ctx.send(f"🌀 Fibonacci #{n} = **{a}**")


@bot.command()
async def isprime(ctx, n: int):
    if n < 2:
        await ctx.send(f"❌ **{n}** is not prime.")
        return
    prime = all(n % i for i in range(2, int(n ** 0.5) + 1))
    await ctx.send(f"{'✅' if prime else '❌'} **{n}** is {'prime' if prime else 'not prime'}.")


@bot.command()
async def gcd(ctx, a: int, b: int):
    await ctx.send(f"🔢 GCD({a}, {b}) = **{_math.gcd(a, b)}**")


@bot.command()
async def lcm(ctx, a: int, b: int):
    if a == 0 or b == 0:
        await ctx.send("🔢 LCM is **0**.")
        return
    await ctx.send(f"🔢 LCM({a}, {b}) = **{abs(a * b) // _math.gcd(a, b)}**")


@bot.command()
async def average(ctx, *numbers: float):
    if not numbers:
        await ctx.send("❌ Provide numbers.")
        return
    await ctx.send(f"📊 Average = **{sum(numbers) / len(numbers):.4g}**")


@bot.command()
async def percentof(ctx, percent: float, whole: float):
    await ctx.send(f"📊 **{percent}%** of {whole} = **{percent / 100 * whole:.4g}**")


@bot.command()
async def tip(ctx, amount: float, percent: float = 15):
    t = amount * percent / 100
    await ctx.send(f"💵 Tip ({percent}%) = **{t:.2f}** | Total = **{amount + t:.2f}**")


@bot.command()
async def temp(ctx, value: str):
    m = re.match(r"(-?\d+\.?\d*)\s*([cCfF])", value.strip())
    if not m:
        await ctx.send("❌ Format: `.temp 100C` or `.temp 212F`")
        return
    val, unit = float(m.group(1)), m.group(2).upper()
    if unit == "C":
        await ctx.send(f"🌡️ {val}°C = **{val * 9/5 + 32:.1f}°F**")
    else:
        await ctx.send(f"🌡️ {val}°F = **{(val - 32) * 5/9:.1f}°C**")


@bot.command()
async def age(ctx, date: str):
    try:
        born = datetime.datetime.strptime(date, "%Y-%m-%d")
        today = datetime.datetime.utcnow()
        years = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        await ctx.send(f"🎂 That's **{years}** years old.")
    except Exception:
        await ctx.send("❌ Format: `.age YYYY-MM-DD`")


@bot.command()
async def daysuntil(ctx, date: str):
    try:
        target = datetime.datetime.strptime(date, "%Y-%m-%d")
        days = (target - datetime.datetime.utcnow()).days
        await ctx.send(f"📅 **{abs(days)}** days {'until' if days >= 0 else 'since'} {date}.")
    except Exception:
        await ctx.send("❌ Format: `.daysuntil YYYY-MM-DD`")


@bot.command()
async def nato(ctx, *, text):
    nato_alpha = {"a":"Alpha","b":"Bravo","c":"Charlie","d":"Delta","e":"Echo","f":"Foxtrot","g":"Golf",
                  "h":"Hotel","i":"India","j":"Juliett","k":"Kilo","l":"Lima","m":"Mike","n":"November",
                  "o":"Oscar","p":"Papa","q":"Quebec","r":"Romeo","s":"Sierra","t":"Tango","u":"Uniform",
                  "v":"Victor","w":"Whiskey","x":"X-ray","y":"Yankee","z":"Zulu"}
    out = " ".join(nato_alpha.get(c, c) for c in text.lower())
    await ctx.send(f"📻 {out[:1900]}")


@bot.command()
async def urban(ctx, *, word):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://api.urbandictionary.com/v0/define?term={word}") as resp:
                data = await resp.json()
            if not data["list"]:
                await ctx.send(f"❌ No definition found for **{word}**.")
                return
            e = data["list"][0]
            defn = e["definition"][:500].replace("[", "").replace("]", "")
            ex = e["example"][:300].replace("[", "").replace("]", "")
            embed = discord.Embed(title=f"📖 {e['word']}", url=e["permalink"], color=discord.Color.blurple())
            embed.add_field(name="Definition", value=defn, inline=False)
            if ex:
                embed.add_field(name="Example", value=f"*{ex}*", inline=False)
            embed.add_field(name="Votes", value=f"👍 {e['thumbs_up']} 👎 {e['thumbs_down']}")
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("❌ Could not fetch definition.")


@bot.command()
async def define(ctx, *, word):
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}") as resp:
                data = await resp.json()
            if not isinstance(data, list):
                await ctx.send(f"❌ No definition found for **{word}**.")
                return
            meanings = data[0]["meanings"]
            embed = discord.Embed(title=f"📚 {word}", color=discord.Color.green())
            for mn in meanings[:3]:
                d = mn["definitions"][0]["definition"]
                embed.add_field(name=mn["partOfSpeech"], value=d[:300], inline=False)
            await ctx.send(embed=embed)
        except Exception:
            await ctx.send("❌ Could not fetch definition.")


@bot.command()
async def color(ctx, hex_code: str):
    hex_code = hex_code.lstrip("#")
    try:
        color_val = int(hex_code, 16)
        r, g, b = tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))
        embed = discord.Embed(title=f"🎨 Color #{hex_code.upper()}", color=discord.Color(color_val))
        embed.add_field(name="Hex", value=f"#{hex_code.upper()}")
        embed.add_field(name="Dec", value=str(color_val))
        embed.add_field(name="RGB", value=f"({r}, {g}, {b})")
        await ctx.send(embed=embed)
    except Exception:
        await ctx.send("❌ Invalid hex code.")


@bot.command()
async def qr(ctx, *, text):
    url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={text.replace(' ', '+')}"
    embed = discord.Embed(title="📱 QR Code", color=discord.Color.blue())
    embed.set_image(url=url)
    embed.add_field(name="Content", value=text[:100])
    await ctx.send(embed=embed)


@bot.command()
async def timer(ctx, seconds: int):
    if not 1 <= seconds <= 300:
        await ctx.send("❌ Timer must be 1-300 seconds.")
        return
    await ctx.send(f"⏳ Timer started for **{seconds}** seconds...")
    await asyncio.sleep(seconds)
    await ctx.send(f"⏰ {ctx.author.mention} Your **{seconds}s** timer is done!")


@bot.command()
async def choose(ctx, *, text):
    options = [o.strip() for o in text.split("|")]
    if len(options) < 2:
        await ctx.send("❌ Format: `.choose option1 | option2`")
        return
    await ctx.send(f"🎯 I choose: **{random.choice(options)}**")


@bot.command()
async def tag(ctx, *, name):
    t = tag_data.get(name.lower())
    if not t:
        await ctx.send(f"❌ Tag `{name}` not found.")
        return
    await ctx.send(t["content"])


@bot.command()
async def addtag(ctx, *, text):
    parts = text.split("|", 1)
    if len(parts) < 2:
        await ctx.send("❌ Format: `.addtag name | content`")
        return
    name, content = parts[0].strip().lower(), parts[1].strip()
    tag_data[name] = {"content": content, "author": str(ctx.author)}
    await ctx.send(f"✅ Tag `{name}` saved!")


@bot.command()
async def deltag(ctx, *, name):
    if name.lower() in tag_data:
        del tag_data[name.lower()]
        await ctx.send(f"🗑️ Tag `{name}` deleted.")
    else:
        await ctx.send(f"❌ Tag `{name}` not found.")


@bot.command()
async def tags(ctx):
    if not tag_data:
        await ctx.send("📭 No tags saved.")
        return
    embed = discord.Embed(title="🏷️ Tags", description=", ".join(f"`{n}`" for n in tag_data), color=discord.Color.blue())
    await ctx.send(embed=embed)


# ── ECONOMY ────────────────────────────────────────────────────────────────────
def _cooldown_left(store, uid, seconds):
    now = time.time()
    last = store.get(uid, 0)
    if now - last < seconds:
        return seconds - (now - last)
    return 0


@bot.command()
async def balance(ctx, member: discord.Member = None):
    member = member or ctx.author
    wallet, bank = economy_data[member.id], bank_data[member.id]
    embed = discord.Embed(title=f"💰 {member.display_name}'s Balance", color=discord.Color.gold())
    embed.add_field(name="Wallet", value=f"🪙 {wallet:,}")
    embed.add_field(name="Bank", value=f"🏦 {bank:,}")
    embed.add_field(name="Net Worth", value=f"💎 {wallet + bank:,}")
    await ctx.send(embed=embed)


@bot.command()
async def networth(ctx, member: discord.Member = None):
    member = member or ctx.author
    total = economy_data[member.id] + bank_data[member.id]
    await ctx.send(f"💎 **{member.display_name}**'s net worth: **{total:,}** coins.")


@bot.command()
async def daily(ctx):
    left = _cooldown_left(daily_cd, ctx.author.id, 86400)
    if left:
        h = int(left // 3600); m = int((left % 3600) // 60)
        await ctx.send(f"⏳ Already claimed! Come back in **{h}h {m}m**.")
        return
    amount = random.randint(200, 500)
    economy_data[ctx.author.id] += amount
    daily_cd[ctx.author.id] = time.time()
    await ctx.send(f"💰 You claimed your daily **{amount}** coins! Balance: **{economy_data[ctx.author.id]:,}**")


@bot.command()
async def weekly(ctx):
    left = _cooldown_left(weekly_cd, ctx.author.id, 604800)
    if left:
        d = int(left // 86400); h = int((left % 86400) // 3600)
        await ctx.send(f"⏳ Already claimed! Come back in **{d}d {h}h**.")
        return
    amount = random.randint(1000, 2500)
    economy_data[ctx.author.id] += amount
    weekly_cd[ctx.author.id] = time.time()
    await ctx.send(f"💰 You claimed your weekly **{amount}** coins! Balance: **{economy_data[ctx.author.id]:,}**")


@bot.command()
async def monthly(ctx):
    left = _cooldown_left(interest_cd, str(ctx.author.id) + "_m", 2592000)
    if left:
        d = int(left // 86400)
        await ctx.send(f"⏳ Already claimed! Come back in **{d}d**.")
        return
    amount = random.randint(5000, 12000)
    economy_data[ctx.author.id] += amount
    interest_cd[str(ctx.author.id) + "_m"] = time.time()
    await ctx.send(f"💰 You claimed your monthly **{amount}** coins! Balance: **{economy_data[ctx.author.id]:,}**")


@bot.command()
async def hourly(ctx):
    left = _cooldown_left(hourly_cd, ctx.author.id, 3600)
    if left:
        await ctx.send(f"⏳ Come back in **{int(left // 60)}m**.")
        return
    amount = random.randint(50, 150)
    economy_data[ctx.author.id] += amount
    hourly_cd[ctx.author.id] = time.time()
    await ctx.send(f"💰 You claimed your hourly **{amount}** coins!")


@bot.command()
async def work(ctx):
    left = _cooldown_left(work_cd, ctx.author.id, 3600)
    if left:
        await ctx.send(f"⏳ You're tired! Rest for **{int(left // 60)}m**.")
        return
    jobs = [("programmer", 300, 600),("chef", 150, 400),("teacher", 200, 450),("doctor", 400, 800),
            ("artist", 100, 500),("streamer", 50, 700),("engineer", 350, 650),("barista", 120, 300)]
    job, lo, hi = random.choice(jobs)
    amount = random.randint(lo, hi)
    economy_data[ctx.author.id] += amount
    work_cd[ctx.author.id] = time.time()
    await ctx.send(f"💼 You worked as a **{job}** and earned **{amount}** coins!")


@bot.command()
async def beg(ctx):
    if random.random() < 0.15:
        await ctx.send("😢 Nobody gave you anything this time.")
        return
    amount = random.randint(10, 100)
    economy_data[ctx.author.id] += amount
    await ctx.send(f"🥺 Someone gave you **{amount}** coins out of pity!")


def _gather(name, emoji, lo, hi, store, cd):
    async def cmd(ctx):
        left = _cooldown_left(store, ctx.author.id, cd)
        if left:
            await ctx.send(f"⏳ Wait **{int(left)}s** before you {name} again.")
            return
        amount = random.randint(lo, hi)
        economy_data[ctx.author.id] += amount
        store[ctx.author.id] = time.time()
        await ctx.send(f"{emoji} You went to {name} and found **{amount}** coins!")
    return cmd


dig      = bot.command(name="dig")(_gather("dig", "⛏️", 20, 250, dig_cd, 60))
fish     = bot.command(name="fish")(_gather("fish", "🎣", 30, 300, fish_cd, 60))
hunt     = bot.command(name="hunt")(_gather("hunt", "🏹", 40, 350, quest_cd, 90))
mine     = bot.command(name="mine")(_gather("mine", "⚒️", 50, 400, interest_cd, 120))
search   = bot.command(name="search")(_gather("search", "🔍", 10, 200, crime_cd, 45))
scavenge = bot.command(name="scavenge")(_gather("scavenge", "🗑️", 15, 220, hourly_cd, 75))


@bot.command()
async def crime(ctx):
    left = _cooldown_left(crime_cd, str(ctx.author.id) + "_c", 300)
    if left:
        await ctx.send(f"⏳ Lay low for **{int(left // 60)}m**.")
        return
    crime_cd[str(ctx.author.id) + "_c"] = time.time()
    if random.random() < 0.45:
        fine = random.randint(100, 400)
        economy_data[ctx.author.id] = max(0, economy_data[ctx.author.id] - fine)
        await ctx.send(f"🚔 You got caught and paid a **{fine}** coin fine!")
    else:
        loot = random.randint(300, 900)
        economy_data[ctx.author.id] += loot
        await ctx.send(f"🦹 Crime pays! You got away with **{loot}** coins!")


@bot.command()
async def quest(ctx):
    left = _cooldown_left(quest_cd, str(ctx.author.id) + "_q", 1800)
    if left:
        await ctx.send(f"⏳ Next quest in **{int(left // 60)}m**.")
        return
    quest_cd[str(ctx.author.id) + "_q"] = time.time()
    quests = ["slayed a dragon","rescued a cat","delivered a package","won a tournament","found a treasure chest"]
    reward = random.randint(400, 1000)
    economy_data[ctx.author.id] += reward
    xp_data[ctx.author.id] += 25
    await ctx.send(f"🗺️ You {random.choice(quests)} and earned **{reward}** coins (+25 XP)!")


@bot.command()
async def give(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("❌ Amount must be positive.")
        return
    if economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Insufficient funds.")
        return
    economy_data[ctx.author.id] -= amount
    economy_data[member.id] += amount
    await ctx.send(f"💸 {ctx.author.mention} gave **{amount}** coins to {member.mention}!")


@bot.command()
async def gift(ctx, member: discord.Member, *, item):
    item = item.lower()
    if item not in inventory_data[ctx.author.id]:
        await ctx.send(f"❌ You don't have a **{item}**.")
        return
    inventory_data[ctx.author.id].remove(item)
    inventory_data[member.id].append(item)
    await ctx.send(f"🎁 {ctx.author.mention} gifted a **{item}** to {member.mention}!")


@bot.command()
async def rob(ctx, member: discord.Member):
    if member.id == ctx.author.id:
        await ctx.send("❌ You can't rob yourself.")
        return
    left = _cooldown_left(rob_cd, ctx.author.id, 600)
    if left:
        await ctx.send(f"⏳ Lay low for **{int(left // 60)}m**.")
        return
    if "shield" in inventory_data[member.id]:
        inventory_data[member.id].remove("shield")
        await ctx.send(f"🛡️ {member.mention}'s shield blocked your robbery!")
        rob_cd[ctx.author.id] = time.time()
        return
    if economy_data[member.id] < 100:
        await ctx.send("❌ Target is too poor to rob.")
        return
    rob_cd[ctx.author.id] = time.time()
    if random.random() < 0.5:
        stolen = random.randint(50, min(500, economy_data[member.id]))
        economy_data[member.id] -= stolen
        economy_data[ctx.author.id] += stolen
        await ctx.send(f"🦹 You robbed **{stolen}** coins from {member.mention}!")
    else:
        fine = random.randint(50, 200)
        economy_data[ctx.author.id] = max(0, economy_data[ctx.author.id] - fine)
        await ctx.send(f"🚔 You got caught and paid a **{fine}** coin fine!")


@bot.command()
async def heist(ctx, member: discord.Member):
    if economy_data[ctx.author.id] < 200:
        await ctx.send("❌ You need at least 200 coins to plan a heist.")
        return
    if random.random() < 0.4:
        loot = random.randint(500, 1500)
        economy_data[ctx.author.id] += loot
        await ctx.send(f"💰 The heist on {member.mention} succeeded! You scored **{loot}** coins!")
    else:
        loss = random.randint(100, 300)
        economy_data[ctx.author.id] = max(0, economy_data[ctx.author.id] - loss)
        await ctx.send(f"🚨 The heist failed! You lost **{loss}** coins.")


@bot.command()
async def leaderboard(ctx):
    totals = {uid: economy_data[uid] + bank_data[uid] for uid in set(list(economy_data) + list(bank_data))}
    ranked = sorted(totals.items(), key=lambda x: x[1], reverse=True)[:10]
    if not ranked:
        await ctx.send("📭 No economy data yet.")
        return
    medals = ["🥇","🥈","🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, total) in enumerate(ranked):
        u = bot.get_user(uid)
        lines.append(f"{medals[i]} **{u.display_name if u else f'ID:{uid}'}** — {total:,} coins")
    embed = discord.Embed(title="🏆 Richest Members", description="\n".join(lines), color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.command()
async def poorest(ctx):
    totals = {uid: economy_data[uid] + bank_data[uid] for uid in set(list(economy_data) + list(bank_data))}
    ranked = sorted(totals.items(), key=lambda x: x[1])[:10]
    if not ranked:
        await ctx.send("📭 No economy data yet.")
        return
    lines = [f"**{(bot.get_user(uid).display_name if bot.get_user(uid) else uid)}** — {total:,} coins" for uid, total in ranked]
    embed = discord.Embed(title="🪙 Poorest Members", description="\n".join(lines), color=discord.Color.greyple())
    await ctx.send(embed=embed)


@bot.command()
async def slots(ctx, bet: int = 50):
    if bet <= 0 or economy_data[ctx.author.id] < bet:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    emojis = ["🍒","🍋","🍊","🍇","💎","7️⃣"]
    result = [random.choice(emojis) for _ in range(3)]
    economy_data[ctx.author.id] -= bet
    if result[0] == result[1] == result[2]:
        win = bet * 10
        economy_data[ctx.author.id] += win
        outcome = f"🎉 JACKPOT! You won **{win}** coins!"
    elif result[0] == result[1] or result[1] == result[2] or result[0] == result[2]:
        win = bet * 2
        economy_data[ctx.author.id] += win
        outcome = f"✨ Two match! You won **{win}** coins!"
    else:
        outcome = f"😔 You lost **{bet}** coins."
    embed = discord.Embed(title="🎰 Slot Machine", color=discord.Color.gold())
    embed.add_field(name="Result", value=" | ".join(result), inline=False)
    embed.add_field(name="Outcome", value=outcome, inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def gamble(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    if random.random() < 0.5:
        economy_data[ctx.author.id] += amount
        await ctx.send(f"🎉 You won **{amount}** coins! Balance: **{economy_data[ctx.author.id]:,}**")
    else:
        economy_data[ctx.author.id] -= amount
        await ctx.send(f"😔 You lost **{amount}** coins. Balance: **{economy_data[ctx.author.id]:,}**")


@bot.command()
async def flip(ctx, amount: int, side: str = "heads"):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    if side.lower() not in ("heads", "tails"):
        await ctx.send("❌ Choose `heads` or `tails`.")
        return
    result = random.choice(["heads", "tails"])
    if result == side.lower():
        economy_data[ctx.author.id] += amount
        await ctx.send(f"🪙 It's **{result}**! You won **{amount}** coins!")
    else:
        economy_data[ctx.author.id] -= amount
        await ctx.send(f"🪙 It's **{result}**! You lost **{amount}** coins.")


@bot.command()
async def dicebet(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    you, me = random.randint(1, 6), random.randint(1, 6)
    if you > me:
        economy_data[ctx.author.id] += amount
        res = f"🎉 You won **{amount}** coins!"
    elif you < me:
        economy_data[ctx.author.id] -= amount
        res = f"😔 You lost **{amount}** coins."
    else:
        res = "🤝 Tie! Bet returned."
    await ctx.send(f"🎲 You rolled **{you}**, I rolled **{me}**. {res}")


@bot.command()
async def blackjack(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    you = random.randint(16, 24)
    dealer = random.randint(16, 24)
    if you > 21:
        economy_data[ctx.author.id] -= amount
        res = f"💥 Bust at {you}! Lost **{amount}**."
    elif dealer > 21 or you > dealer:
        economy_data[ctx.author.id] += amount
        res = f"🎉 You {you} beat dealer {dealer}! Won **{amount}**."
    elif you < dealer:
        economy_data[ctx.author.id] -= amount
        res = f"😔 Dealer {dealer} beat you {you}. Lost **{amount}**."
    else:
        res = f"🤝 Push at {you}."
    await ctx.send(f"🃏 {res}")


@bot.command()
async def roulette(ctx, amount: int, color: str = "red"):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    if color.lower() not in ("red", "black", "green"):
        await ctx.send("❌ Choose `red`, `black`, or `green`.")
        return
    roll = random.randint(0, 36)
    result = "green" if roll == 0 else "red" if roll % 2 else "black"
    if color.lower() == result:
        mult = 14 if result == "green" else 2
        win = amount * mult
        economy_data[ctx.author.id] += win
        await ctx.send(f"🎡 Ball landed on **{roll} ({result})** — you won **{win}** coins!")
    else:
        economy_data[ctx.author.id] -= amount
        await ctx.send(f"🎡 Ball landed on **{roll} ({result})** — you lost **{amount}** coins.")


@bot.command()
async def highlow(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    first = random.randint(1, 100)
    await ctx.send(f"🔢 First number is **{first}**. Will the next be **higher** or **lower**? (type higher/lower, 10s)")
    def check(m):
        return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() in ("higher", "lower")
    try:
        msg = await bot.wait_for("message", check=check, timeout=10.0)
        second = random.randint(1, 100)
        correct = (second > first and msg.content.lower() == "higher") or (second < first and msg.content.lower() == "lower")
        if correct:
            economy_data[ctx.author.id] += amount
            await ctx.send(f"🎉 Next was **{second}** — you won **{amount}** coins!")
        else:
            economy_data[ctx.author.id] -= amount
            await ctx.send(f"😔 Next was **{second}** — you lost **{amount}** coins.")
    except asyncio.TimeoutError:
        await ctx.send("⏰ Too slow! Bet cancelled.")


@bot.command()
async def scratch(ctx, amount: int = 100):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    economy_data[ctx.author.id] -= amount
    symbols = [random.choice(["💰","🍀","⭐","❌","💎","🔔"]) for _ in range(3)]
    if symbols.count("💎") == 3:
        win = amount * 20
    elif len(set(symbols)) == 1:
        win = amount * 5
    elif "💰" in symbols:
        win = amount * 2
    else:
        win = 0
    economy_data[ctx.author.id] += win
    msg = f"won **{win}** coins!" if win else "won nothing."
    await ctx.send(f"🎟️ {' '.join(symbols)} — you {msg}")


@bot.command()
async def wheel(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid bet or insufficient funds.")
        return
    economy_data[ctx.author.id] -= amount
    mult = random.choice([0, 0, 0.5, 1, 1.5, 2, 3, 5])
    win = int(amount * mult)
    economy_data[ctx.author.id] += win
    await ctx.send(f"🎡 The wheel landed on **x{mult}** — you got **{win}** coins back!")


@bot.command()
async def invest(ctx, amount: int):
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid amount or insufficient funds.")
        return
    economy_data[ctx.author.id] -= amount
    ret = random.uniform(0.5, 1.8)
    payout = int(amount * ret)
    economy_data[ctx.author.id] += payout
    pct = (ret - 1) * 100
    await ctx.send(f"📈 Your investment returned **{pct:+.1f}%** → **{payout}** coins.")


@bot.command()
async def stocks(ctx):
    names = ["ACME", "TECH", "GOLD", "OILX", "MEME", "BANK"]
    embed = discord.Embed(title="📈 Stock Prices", color=discord.Color.green())
    for n in names:
        price = random.randint(10, 500)
        change = random.uniform(-8, 8)
        embed.add_field(name=n, value=f"{price} ({change:+.1f}%)", inline=True)
    await ctx.send(embed=embed)


@bot.command()
async def deposit(ctx, amount):
    if str(amount).lower() == "all":
        amount = economy_data[ctx.author.id]
    else:
        amount = int(amount)
    if amount <= 0 or economy_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid amount or insufficient funds.")
        return
    economy_data[ctx.author.id] -= amount
    bank_data[ctx.author.id] += amount
    await ctx.send(f"🏦 Deposited **{amount}** coins. Bank: **{bank_data[ctx.author.id]:,}**")


@bot.command()
async def withdraw(ctx, amount):
    if str(amount).lower() == "all":
        amount = bank_data[ctx.author.id]
    else:
        amount = int(amount)
    if amount <= 0 or bank_data[ctx.author.id] < amount:
        await ctx.send("❌ Invalid amount or insufficient bank funds.")
        return
    bank_data[ctx.author.id] -= amount
    economy_data[ctx.author.id] += amount
    await ctx.send(f"🏦 Withdrew **{amount}** coins. Wallet: **{economy_data[ctx.author.id]:,}**")


@bot.command()
async def bankbalance(ctx):
    await ctx.send(f"🏦 Your bank balance: **{bank_data[ctx.author.id]:,}** coins.")


@bot.command()
async def interest(ctx):
    left = _cooldown_left(interest_cd, str(ctx.author.id) + "_i", 86400)
    if left:
        await ctx.send(f"⏳ Interest already claimed. Back in **{int(left // 3600)}h**.")
        return
    if bank_data[ctx.author.id] <= 0:
        await ctx.send("❌ You need coins in the bank to earn interest.")
        return
    gained = int(bank_data[ctx.author.id] * 0.02)
    bank_data[ctx.author.id] += gained
    interest_cd[str(ctx.author.id) + "_i"] = time.time()
    await ctx.send(f"📈 You earned **{gained}** coins in interest (2%)!")


@bot.command()
async def shop(ctx):
    embed = discord.Embed(title="🛒 Shop", description="Use `.buy <item>` to purchase.", color=discord.Color.gold())
    for name, item in shop_items.items():
        embed.add_field(name=f"{name} — 🪙 {item['price']:,}", value=item["desc"], inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def buy(ctx, *, item):
    item = item.lower()
    if item not in shop_items:
        await ctx.send(f"❌ Item not found. Use `.shop` to see items.")
        return
    price = shop_items[item]["price"]
    if economy_data[ctx.author.id] < price:
        await ctx.send(f"❌ You need **{price:,}** coins.")
        return
    economy_data[ctx.author.id] -= price
    inventory_data[ctx.author.id].append(item)
    await ctx.send(f"✅ You bought **{item}** for **{price:,}** coins!")


@bot.command()
async def sell(ctx, *, item):
    item = item.lower()
    if item not in inventory_data[ctx.author.id]:
        await ctx.send(f"❌ You don't own a **{item}**.")
        return
    price = shop_items.get(item, {}).get("price", 100)
    refund = price // 2
    inventory_data[ctx.author.id].remove(item)
    economy_data[ctx.author.id] += refund
    await ctx.send(f"💸 You sold **{item}** for **{refund:,}** coins.")


@bot.command()
async def use(ctx, *, item):
    item = item.lower()
    if item not in inventory_data[ctx.author.id]:
        await ctx.send(f"❌ You don't own a **{item}**.")
        return
    if item == "lootbox":
        inventory_data[ctx.author.id].remove(item)
        reward = random.randint(100, 1000)
        economy_data[ctx.author.id] += reward
        await ctx.send(f"📦 You opened a lootbox and got **{reward}** coins!")
    elif item == "boost":
        inventory_data[ctx.author.id].remove(item)
        await ctx.send("⚡ XP boost activated! (cosmetic in this build)")
    else:
        await ctx.send(f"🔧 You used **{item}**.")


@bot.command()
async def inventory(ctx, member: discord.Member = None):
    member = member or ctx.author
    items = inventory_data.get(member.id, [])
    if not items:
        await ctx.send(f"🎒 **{member.display_name}**'s inventory is empty.")
        return
    counts = Counter(items)
    desc = "\n".join(f"• **{name}** x{cnt}" for name, cnt in counts.items())
    embed = discord.Embed(title=f"🎒 {member.display_name}'s Inventory", description=desc, color=discord.Color.gold())
    await ctx.send(embed=embed)


@bot.command()
async def lottery(ctx):
    global lottery_pot
    cost = 100
    if economy_data[ctx.author.id] < cost:
        await ctx.send(f"❌ A ticket costs **{cost}** coins.")
        return
    economy_data[ctx.author.id] -= cost
    lottery_entries.append(ctx.author.id)
    lottery_pot += cost
    await ctx.send(f"🎟️ You bought a lottery ticket! Pot is now **{lottery_pot:,}** coins. Use `.drawlottery` to draw.")


@bot.command()
async def jackpot(ctx):
    await ctx.send(f"🎰 Current lottery pot: **{lottery_pot:,}** coins across **{len(lottery_entries)}** ticket(s).")


@bot.command()
@commands.has_permissions(administrator=True)
async def drawlottery(ctx):
    global lottery_pot, lottery_entries
    if not lottery_entries:
        await ctx.send("❌ No lottery entries.")
        return
    winner_id = random.choice(lottery_entries)
    winner = bot.get_user(winner_id)
    economy_data[winner_id] += lottery_pot
    await ctx.send(f"🎉 **{winner.display_name if winner else winner_id}** won the lottery pot of **{lottery_pot:,}** coins!")
    lottery_pot = 0
    lottery_entries = []


@bot.command()
@commands.has_permissions(administrator=True)
async def coinrain(ctx, amount: int):
    members = [m for m in ctx.guild.members if not m.bot and str(m.status) != "offline"]
    if not members:
        await ctx.send("❌ No online members.")
        return
    for m in members:
        economy_data[m.id] += amount
    await ctx.send(f"🌧️ It's raining coins! **{amount}** coins to **{len(members)}** online members!")


@bot.command()
@commands.has_permissions(administrator=True)
async def addcoins(ctx, member: discord.Member, amount: int):
    economy_data[member.id] += amount
    await ctx.send(f"✅ Added **{amount}** coins to {member.mention}. New: **{economy_data[member.id]:,}**")


@bot.command()
@commands.has_permissions(administrator=True)
async def removecoins(ctx, member: discord.Member, amount: int):
    economy_data[member.id] = max(0, economy_data[member.id] - amount)
    await ctx.send(f"✅ Removed **{amount}** coins from {member.mention}. New: **{economy_data[member.id]:,}**")


@bot.command()
@commands.has_permissions(administrator=True)
async def setcoins(ctx, member: discord.Member, amount: int):
    economy_data[member.id] = max(0, amount)
    await ctx.send(f"✅ Set {member.mention}'s wallet to **{amount:,}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetcoins(ctx, member: discord.Member):
    economy_data[member.id] = 500
    await ctx.send(f"✅ Reset {member.mention}'s wallet to **500**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetbank(ctx, member: discord.Member):
    bank_data[member.id] = 0
    await ctx.send(f"✅ Reset {member.mention}'s bank to **0**.")


# ── LEVELS ─────────────────────────────────────────────────────────────────────
def _required_xp(lvl):
    return (lvl + 1) * CONFIG["xp_base"]


def _rank_of(uid):
    ranked = sorted(level_data.items(), key=lambda x: (x[1], xp_data[x[0]]), reverse=True)
    for i, (u, _) in enumerate(ranked, 1):
        if u == uid:
            return i, len(ranked)
    return None, len(ranked)


async def _send_level(ctx, member):
    lvl = level_data[member.id]
    xp = xp_data[member.id]
    need = _required_xp(lvl)
    pct = int(xp / need * 10) if need else 0
    bar = "█" * pct + "░" * (10 - pct)
    embed = discord.Embed(title=f"⭐ {member.display_name}'s Level", color=discord.Color.pink())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Level", value=str(lvl))
    embed.add_field(name="XP", value=f"{xp}/{need}")
    rank, total = _rank_of(member.id)
    embed.add_field(name="Rank", value=f"#{rank}/{total}" if rank else "Unranked")
    embed.add_field(name="Progress", value=f"`{bar}` {int(xp/need*100) if need else 0}%", inline=False)
    await ctx.send(embed=embed)


@bot.command()
async def level(ctx, member: discord.Member = None):
    await _send_level(ctx, member or ctx.author)


@bot.command()
async def lvl(ctx, member: discord.Member = None):
    await _send_level(ctx, member or ctx.author)


@bot.command()
async def levelcheck(ctx, member: discord.Member = None):
    await _send_level(ctx, member or ctx.author)


@bot.command()
async def rankcard(ctx, member: discord.Member = None):
    await _send_level(ctx, member or ctx.author)


@bot.command()
async def levelof(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"⭐ **{member.display_name}** is level **{level_data[member.id]}**.")


@bot.command()
async def rank(ctx, member: discord.Member = None):
    member = member or ctx.author
    r, total = _rank_of(member.id)
    await ctx.send(f"🏅 **{member.display_name}** is ranked **#{r or '?'}/{total}** (Level {level_data[member.id]}).")


@bot.command()
async def rankof(ctx, member: discord.Member = None):
    await rank(ctx, member)


@bot.command()
async def myrank(ctx):
    await rank(ctx, ctx.author)


@bot.command()
async def mylevel(ctx):
    await ctx.send(f"⭐ You are level **{level_data[ctx.author.id]}**.")


@bot.command()
async def myxp(ctx):
    await ctx.send(f"✨ You have **{xp_data[ctx.author.id]}** XP toward level {level_data[ctx.author.id] + 1}.")


@bot.command()
async def xp(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"✨ **{member.display_name}** — Level {level_data[member.id]}, {xp_data[member.id]}/{_required_xp(level_data[member.id])} XP.")


@bot.command()
async def exp(ctx, member: discord.Member = None):
    await xp(ctx, member)


@bot.command()
async def experience(ctx, member: discord.Member = None):
    await xp(ctx, member)


@bot.command()
async def xpinfo(ctx, member: discord.Member = None):
    member = member or ctx.author
    lvl = level_data[member.id]
    embed = discord.Embed(title=f"✨ XP Info — {member.display_name}", color=discord.Color.pink())
    embed.add_field(name="Level", value=str(lvl))
    embed.add_field(name="Current XP", value=str(xp_data[member.id]))
    embed.add_field(name="Needed", value=str(_required_xp(lvl)))
    embed.add_field(name="XP/msg", value=str(CONFIG["xp_per_msg"]))
    await ctx.send(embed=embed)


@bot.command()
async def nextlevel(ctx, member: discord.Member = None):
    member = member or ctx.author
    remaining = _required_xp(level_data[member.id]) - xp_data[member.id]
    await ctx.send(f"📈 **{member.display_name}** needs **{remaining}** more XP for level **{level_data[member.id] + 1}**.")


@bot.command()
async def xpneeded(ctx, member: discord.Member = None):
    await nextlevel(ctx, member)


@bot.command()
async def levelprogress(ctx, member: discord.Member = None):
    member = member or ctx.author
    need = _required_xp(level_data[member.id])
    pct = xp_data[member.id] / need * 100 if need else 0
    await ctx.send(f"📊 **{member.display_name}** is **{pct:.1f}%** to the next level.")


@bot.command()
async def progressbar(ctx, member: discord.Member = None):
    member = member or ctx.author
    need = _required_xp(level_data[member.id])
    filled = int(xp_data[member.id] / need * 20) if need else 0
    bar = "█" * filled + "░" * (20 - filled)
    await ctx.send(f"`{bar}` {int(xp_data[member.id]/need*100) if need else 0}%")


async def _level_board(ctx, by_xp=False, reverse=True, title="🏆 Level Leaderboard"):
    key = (lambda x: xp_data[x[0]]) if by_xp else (lambda x: (x[1], xp_data[x[0]]))
    ranked = sorted(level_data.items(), key=key, reverse=reverse)[:10]
    if not ranked:
        await ctx.send("📭 No level data yet.")
        return
    medals = ["🥇","🥈","🥉"] + ["🏅"] * 7
    lines = []
    for i, (uid, lvl) in enumerate(ranked):
        u = bot.get_user(uid)
        val = f"{xp_data[uid]} XP" if by_xp else f"Level {lvl}"
        lines.append(f"{medals[i]} **{u.display_name if u else uid}** — {val}")
    await ctx.send(embed=discord.Embed(title=title, description="\n".join(lines), color=discord.Color.pink()))


@bot.command()
async def top(ctx):
    await _level_board(ctx, title="🏆 Top by Level")


@bot.command()
async def toplevels(ctx):
    await _level_board(ctx, title="🏆 Top by Level")


@bot.command()
async def levelboard(ctx):
    await _level_board(ctx, title="🏆 Level Leaderboard")


@bot.command()
async def bottomlevels(ctx):
    await _level_board(ctx, reverse=False, title="📉 Lowest Levels")


@bot.command()
async def xpboard(ctx):
    await _level_board(ctx, by_xp=True, title="✨ Top by XP")


@bot.command()
async def xpleaderboard(ctx):
    await _level_board(ctx, by_xp=True, title="✨ Top by XP")


@bot.command()
async def highestlevel(ctx):
    if not level_data:
        await ctx.send("📭 No level data.")
        return
    uid, lvl = max(level_data.items(), key=lambda x: x[1])
    u = bot.get_user(uid)
    await ctx.send(f"👑 Highest: **{u.display_name if u else uid}** at level **{lvl}**.")


@bot.command()
async def lowestlevel(ctx):
    if not level_data:
        await ctx.send("📭 No level data.")
        return
    uid, lvl = min(level_data.items(), key=lambda x: x[1])
    u = bot.get_user(uid)
    await ctx.send(f"🐣 Lowest: **{u.display_name if u else uid}** at level **{lvl}**.")


@bot.command()
async def averagelevel(ctx):
    if not level_data:
        await ctx.send("📭 No level data.")
        return
    avg = sum(level_data.values()) / len(level_data)
    await ctx.send(f"📊 Average level: **{avg:.2f}** across **{len(level_data)}** members.")


@bot.command()
async def totalxp(ctx):
    total = sum(level_data[u] * CONFIG["xp_base"] + xp_data[u] for u in set(list(level_data) + list(xp_data)))
    await ctx.send(f"✨ Total server XP: **{total:,}**.")


@bot.command()
async def levelstats(ctx):
    if not level_data:
        await ctx.send("📭 No level data.")
        return
    embed = discord.Embed(title="📊 Level Statistics", color=discord.Color.pink())
    embed.add_field(name="Tracked Members", value=str(len(level_data)))
    embed.add_field(name="Highest Level", value=str(max(level_data.values())))
    embed.add_field(name="Average Level", value=f"{sum(level_data.values()) / len(level_data):.2f}")
    await ctx.send(embed=embed)


@bot.command()
async def whoislevel(ctx, n: int):
    members = [bot.get_user(u) for u, l in level_data.items() if l == n]
    members = [m for m in members if m]
    if not members:
        await ctx.send(f"📭 Nobody is at level **{n}**.")
        return
    await ctx.send(f"⭐ Level **{n}**: " + ", ".join(m.display_name for m in members[:20]))


@bot.command()
@commands.has_permissions(administrator=True)
async def givexp(ctx, member: discord.Member, amount: int):
    xp_data[member.id] += amount
    await ctx.send(f"✅ Gave **{amount}** XP to {member.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def addxp(ctx, member: discord.Member, amount: int):
    xp_data[member.id] += amount
    await ctx.send(f"✅ Added **{amount}** XP to {member.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removexp(ctx, member: discord.Member, amount: int):
    xp_data[member.id] = max(0, xp_data[member.id] - amount)
    await ctx.send(f"✅ Removed **{amount}** XP from {member.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setxp(ctx, member: discord.Member, amount: int):
    xp_data[member.id] = max(0, amount)
    await ctx.send(f"✅ Set {member.mention}'s XP to **{amount}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def addlevel(ctx, member: discord.Member, n: int):
    level_data[member.id] += n
    await ctx.send(f"✅ Added **{n}** level(s) to {member.mention}. Now level **{level_data[member.id]}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removelevel(ctx, member: discord.Member, n: int):
    level_data[member.id] = max(0, level_data[member.id] - n)
    await ctx.send(f"✅ Removed **{n}** level(s) from {member.mention}. Now level **{level_data[member.id]}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def givelevel(ctx, member: discord.Member, n: int):
    level_data[member.id] += n
    await ctx.send(f"✅ Gave **{n}** level(s) to {member.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setlevel(ctx, member: discord.Member, n: int):
    level_data[member.id] = max(0, n)
    xp_data[member.id] = 0
    await ctx.send(f"✅ Set {member.mention} to level **{n}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def maxlevel(ctx, member: discord.Member):
    level_data[member.id] = 100
    await ctx.send(f"✅ Set {member.mention} to level **100**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetxp(ctx, member: discord.Member):
    xp_data[member.id] = 0
    level_data[member.id] = 0
    await ctx.send(f"✅ Reset {member.mention}'s level and XP.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetlevel(ctx, member: discord.Member):
    level_data[member.id] = 0
    xp_data[member.id] = 0
    await ctx.send(f"✅ Reset {member.mention}'s level.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetallxp(ctx):
    xp_data.clear()
    await ctx.send("✅ Reset XP for all members.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetalllevels(ctx):
    level_data.clear()
    xp_data.clear()
    await ctx.send("✅ Reset levels for all members.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setlevelrole(ctx, n: int, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    level_roles.setdefault(ctx.guild.id, {})[n] = role.id
    await ctx.send(f"✅ Members reaching level **{n}** will get **{role.name}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removelevelrole(ctx, n: int):
    if ctx.guild.id in level_roles and n in level_roles[ctx.guild.id]:
        del level_roles[ctx.guild.id][n]
        await ctx.send(f"✅ Removed reward role for level **{n}**.")
    else:
        await ctx.send("❌ No reward role set for that level.")


@bot.command()
async def levelroles(ctx):
    roles = level_roles.get(ctx.guild.id, {})
    if not roles:
        await ctx.send("📭 No level reward roles set.")
        return
    lines = []
    for lvl, rid in sorted(roles.items()):
        role = ctx.guild.get_role(rid)
        lines.append(f"Level **{lvl}** → {role.mention if role else 'deleted role'}")
    await ctx.send(embed=discord.Embed(title="🎭 Level Reward Roles", description="\n".join(lines), color=discord.Color.pink()))


@bot.command()
@commands.has_permissions(administrator=True)
async def clearlevelroles(ctx):
    level_roles[ctx.guild.id] = {}
    await ctx.send("✅ Cleared all level reward roles.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setxpgain(ctx, amount: int):
    if not 1 <= amount <= 1000:
        await ctx.send("❌ Must be 1-1000.")
        return
    CONFIG["xp_per_msg"] = amount
    await ctx.send(f"✅ XP per message set to **{amount}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setbasexp(ctx, amount: int):
    if not 10 <= amount <= 100000:
        await ctx.send("❌ Must be 10-100000.")
        return
    CONFIG["xp_base"] = amount
    await ctx.send(f"✅ Base XP per level set to **{amount}**.")


@bot.command()
async def xpconfig(ctx):
    embed = discord.Embed(title="⚙️ XP Config", color=discord.Color.pink())
    embed.add_field(name="XP per message", value=str(CONFIG["xp_per_msg"]))
    embed.add_field(name="Base XP per level", value=str(CONFIG["xp_base"]))
    await ctx.send(embed=embed)


@bot.command()
@commands.has_permissions(administrator=True)
async def resetxpconfig(ctx):
    CONFIG["xp_per_msg"] = 10
    CONFIG["xp_base"] = 100
    await ctx.send("✅ XP config reset to defaults (10 / 100).")


# ── SERVER ─────────────────────────────────────────────────────────────────────
@bot.command()
@commands.has_permissions(administrator=True)
async def setjoinlog(ctx, channel: discord.TextChannel):
    join_logs[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Join/leave logs set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removejoinlog(ctx):
    join_logs.pop(ctx.guild.id, None)
    await ctx.send("✅ Join/leave logs removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def autorole(ctx, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    autorole_data[ctx.guild.id] = role.id
    await ctx.send(f"✅ New members will get **{role.name}**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removeautorole(ctx):
    autorole_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Auto-role removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setwelcome(ctx, channel: discord.TextChannel, *, message):
    welcome_data[ctx.guild.id] = {"channel": channel.id, "message": message}
    await ctx.send(f"✅ Welcome message set in {channel.mention}.\nPlaceholders: `{{user}}`, `{{server}}`, `{{count}}`")


@bot.command()
@commands.has_permissions(administrator=True)
async def removewelcome(ctx):
    welcome_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Welcome message removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setgoodbye(ctx, channel: discord.TextChannel, *, message):
    goodbye_data[ctx.guild.id] = {"channel": channel.id, "message": message}
    await ctx.send(f"✅ Goodbye message set in {channel.mention}.\nPlaceholders: `{{user}}`, `{{server}}`")


@bot.command()
@commands.has_permissions(administrator=True)
async def removegoodbye(ctx):
    goodbye_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Goodbye message removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setboost(ctx, channel: discord.TextChannel, *, message):
    boost_data[ctx.guild.id] = {"channel": channel.id, "message": message}
    await ctx.send(f"✅ Boost message set in {channel.mention}.\nPlaceholders: `{{user}}`, `{{server}}`")


@bot.command()
@commands.has_permissions(administrator=True)
async def removeboost(ctx):
    boost_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Boost message removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setlevelchannel(ctx, channel: discord.TextChannel):
    level_channel[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Level-up announcements will go to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removelevelchannel(ctx):
    level_channel.pop(ctx.guild.id, None)
    await ctx.send("✅ Level-up channel removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setmuterole(ctx, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    muterole_data[ctx.guild.id] = role.id
    await ctx.send(f"✅ Mute role set to **{role.name}**.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def setautoreact(ctx, channel: discord.TextChannel, emoji: str):
    autoreact_data[channel.id] = emoji
    await ctx.send(f"✅ I'll auto-react with {emoji} in {channel.mention}.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def removeautoreact(ctx, channel: discord.TextChannel):
    autoreact_data.pop(channel.id, None)
    await ctx.send(f"✅ Stopped auto-reacting in {channel.mention}.")


@bot.command()
@commands.has_permissions(manage_guild=True)
async def giveaway(ctx, minutes: int, *, prize):
    end = datetime.datetime.utcnow() + datetime.timedelta(minutes=minutes)
    embed = discord.Embed(title="🎉 GIVEAWAY 🎉", description=f"**Prize:** {prize}\nReact with 🎉 to enter!",
                          color=discord.Color.magenta(), timestamp=end)
    embed.set_footer(text="Ends at")
    msg = await ctx.send(embed=embed)
    await msg.add_reaction("🎉")
    giveaway_data[msg.id] = {"prize": prize, "channel": ctx.channel.id}
    await asyncio.sleep(minutes * 60)
    try:
        msg = await ctx.channel.fetch_message(msg.id)
        users = [u async for u in msg.reactions[0].users() if not u.bot]
        if users:
            winner = random.choice(users)
            await ctx.send(f"🎉 Congratulations {winner.mention}! You won **{prize}**!")
        else:
            await ctx.send("😔 No valid entries for the giveaway.")
    except Exception:
        pass


@bot.command()
@commands.has_permissions(manage_guild=True)
async def greroll(ctx, message_id: int):
    if message_id not in giveaway_data:
        await ctx.send("❌ Giveaway not found.")
        return
    try:
        msg = await ctx.channel.fetch_message(message_id)
        users = [u async for u in msg.reactions[0].users() if not u.bot]
        if users:
            await ctx.send(f"🎉 New winner: {random.choice(users).mention}!")
        else:
            await ctx.send("😔 No valid entries.")
    except Exception:
        await ctx.send("❌ Could not reroll.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def announce(ctx, channel: discord.TextChannel, *, message):
    embed = discord.Embed(title="📢 Announcement", description=message, color=discord.Color.blue(),
                          timestamp=datetime.datetime.utcnow())
    embed.set_footer(text=f"By {ctx.author}", icon_url=ctx.author.display_avatar.url)
    await channel.send(embed=embed)
    await ctx.send(f"✅ Announcement sent to {channel.mention}.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def embed(ctx, *, text):
    parts = text.split("|", 1)
    title = parts[0].strip()
    desc = parts[1].strip() if len(parts) > 1 else ""
    await ctx.send(embed=discord.Embed(title=title, description=desc, color=discord.Color.blurple()))


@bot.command()
@commands.has_permissions(manage_messages=True)
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)


@bot.command()
@commands.has_permissions(administrator=True)
async def dm(ctx, member: discord.Member, *, message):
    try:
        await member.send(f"📨 Message from **{ctx.guild.name}**:\n{message}")
        await ctx.send(f"✅ DM sent to {member.mention}.")
    except Exception:
        await ctx.send("❌ Could not DM that user.")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def sticky(ctx, *, message):
    sticky_messages[ctx.channel.id] = {"content": message, "last_msg": None}
    await ctx.send("📌 Sticky message set!")


@bot.command()
@commands.has_permissions(manage_messages=True)
async def unsticky(ctx):
    sticky_messages.pop(ctx.channel.id, None)
    await ctx.send("✅ Sticky message removed.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def reactionrole(ctx, message_id: int, emoji: str, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.add_reaction(emoji)
        reaction_roles.setdefault(message_id, {})[emoji] = role.id
        await ctx.send(f"✅ Reaction role set: {emoji} → **{role.name}**.")
    except Exception:
        await ctx.send("❌ Message not found.")


@bot.command()
@commands.has_permissions(manage_roles=True)
async def removereactionrole(ctx, message_id: int):
    if reaction_roles.pop(message_id, None):
        await ctx.send("✅ Reaction roles removed for that message.")
    else:
        await ctx.send("❌ No reaction roles on that message.")


@bot.command()
async def reactionroles(ctx):
    if not reaction_roles:
        await ctx.send("📭 No reaction roles configured.")
        return
    lines = []
    for mid, mapping in list(reaction_roles.items())[:15]:
        pairs = ", ".join(f"{e}→<@&{r}>" for e, r in mapping.items())
        lines.append(f"`{mid}`: {pairs}")
    await ctx.send(embed=discord.Embed(title="🎭 Reaction Roles", description="\n".join(lines), color=discord.Color.teal()))


@bot.command()
@commands.has_permissions(administrator=True)
async def setstarboard(ctx, channel: discord.TextChannel):
    starboard_data[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Starboard set to {channel.mention} (⭐ threshold: 3).")


@bot.command()
@commands.has_permissions(administrator=True)
async def removestarboard(ctx):
    starboard_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Starboard removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setstarcount(ctx, number: int):
    if number < 1:
        await ctx.send("❌ Must be at least 1.")
        return
    starboard_data["_count_" + str(ctx.guild.id)] = number
    await ctx.send(f"✅ Starboard threshold set to **{number}** ⭐.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setcounting(ctx, channel: discord.TextChannel):
    counting_data[ctx.guild.id] = {"channel": channel.id, "count": 0}
    await ctx.send(f"✅ Counting game started in {channel.mention}! Start at **1**.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removecounting(ctx):
    counting_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Counting game stopped.")


@bot.command()
@commands.has_permissions(administrator=True)
async def resetcounting(ctx):
    if ctx.guild.id in counting_data:
        counting_data[ctx.guild.id]["count"] = 0
        await ctx.send("✅ Counter reset to **0**.")
    else:
        await ctx.send("❌ Counting isn't set up.")


@bot.command()
async def countstatus(ctx):
    if ctx.guild.id in counting_data:
        await ctx.send(f"🔢 Current count: **{counting_data[ctx.guild.id]['count']}**. Next: **{counting_data[ctx.guild.id]['count'] + 1}**.")
    else:
        await ctx.send("❌ Counting isn't set up.")


@bot.command()
@commands.has_permissions(administrator=True)
async def setlogchannel(ctx, channel: discord.TextChannel):
    log_channel_data[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Mod log set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removelogchannel(ctx):
    log_channel_data.pop(ctx.guild.id, None)
    await ctx.send("✅ Mod log removed.")


@bot.command()
@commands.has_permissions(administrator=True)
async def confession(ctx, channel: discord.TextChannel):
    confession_ch[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Confession channel set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removeconfession(ctx):
    confession_ch.pop(ctx.guild.id, None)
    await ctx.send("✅ Confession channel removed.")


@bot.command()
async def confess(ctx, *, text):
    if ctx.guild.id not in confession_ch:
        await ctx.send("❌ Confessions aren't set up here.")
        return
    ch = bot.get_channel(confession_ch[ctx.guild.id])
    if ch:
        embed = discord.Embed(title="🤫 Anonymous Confession", description=text, color=discord.Color.dark_purple())
        await ch.send(embed=embed)
        try:
            await ctx.message.delete()
        except Exception:
            pass
        await ctx.send("✅ Your confession was posted anonymously.", delete_after=5)


@bot.command()
@commands.has_permissions(administrator=True)
async def suggest(ctx, channel: discord.TextChannel):
    suggestion_ch[ctx.guild.id] = channel.id
    await ctx.send(f"✅ Suggestion channel set to {channel.mention}.")


@bot.command()
@commands.has_permissions(administrator=True)
async def removesuggestion(ctx):
    suggestion_ch.pop(ctx.guild.id, None)
    await ctx.send("✅ Suggestion channel removed.")


@bot.command(name="suggest_idea")
async def suggest_idea(ctx, *, text):
    if ctx.guild.id not in suggestion_ch:
        await ctx.send("❌ Suggestions aren't set up here.")
        return
    ch = bot.get_channel(suggestion_ch[ctx.guild.id])
    if ch:
        embed = discord.Embed(description=text, color=discord.Color.green())
        embed.set_author(name=str(ctx.author), icon_url=ctx.author.display_avatar.url)
        m = await ch.send(embed=embed)
        await m.add_reaction("👍")
        await m.add_reaction("👎")
        await ctx.send("✅ Suggestion submitted!")


@bot.command()
async def setbirthday(ctx, date: str):
    if not re.match(r"^\d{2}-\d{2}$", date):
        await ctx.send("❌ Format: `.setbirthday MM-DD`")
        return
    birthday_data[ctx.author.id] = {"date": date, "channel": ctx.channel.id}
    await ctx.send(f"🎂 Birthday set to **{date}**!")


@bot.command()
async def removebirthday(ctx):
    birthday_data.pop(ctx.author.id, None)
    await ctx.send("✅ Birthday removed.")


@bot.command()
async def birthdays(ctx):
    if not birthday_data:
        await ctx.send("📭 No birthdays registered.")
        return
    lines = []
    for uid, data in birthday_data.items():
        u = bot.get_user(uid)
        if u:
            lines.append(f"🎂 **{u.display_name}** — {data['date']}")
    await ctx.send(embed=discord.Embed(title="🎂 Birthdays", description="\n".join(lines) or "None", color=discord.Color.pink()))


@bot.command()
async def nextbirthday(ctx):
    if not birthday_data:
        await ctx.send("📭 No birthdays registered.")
        return
    today = datetime.datetime.utcnow()
    def days_away(d):
        m, day = map(int, d.split("-"))
        try:
            nxt = datetime.datetime(today.year, m, day)
        except ValueError:
            return 999
        if nxt < today:
            nxt = datetime.datetime(today.year + 1, m, day)
        return (nxt - today).days
    upcoming = sorted(birthday_data.items(), key=lambda x: days_away(x[1]["date"]))
    uid, data = upcoming[0]
    u = bot.get_user(uid)
    await ctx.send(f"🎂 Next up: **{u.display_name if u else uid}** on **{data['date']}** (in {days_away(data['date'])} days).")


@bot.command()
async def birthdaycount(ctx):
    await ctx.send(f"🎂 **{len(birthday_data)}** birthday(s) registered.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def clone(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    new_ch = await channel.clone()
    await ctx.send(f"✅ Cloned {channel.mention} → {new_ch.mention}.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def createcategory(ctx, *, name):
    cat = await ctx.guild.create_category(name)
    await ctx.send(f"✅ Created category **{cat.name}**.")


@bot.command()
@commands.has_permissions(manage_channels=True)
async def createvoicechannel(ctx, *, name):
    vc = await ctx.guild.create_voice_channel(name)
    await ctx.send(f"✅ Created voice channel **{vc.name}**.")


@bot.command()
@commands.has_permissions(manage_guild=True)
async def setservername(ctx, *, name):
    await ctx.guild.edit(name=name)
    await ctx.send(f"✅ Server renamed to **{name}**.")


@bot.command()
async def settings(ctx):
    g = ctx.guild
    def status(d, key=None):
        return "✅" if (g.id in d) else "❌"
    embed = discord.Embed(title=f"⚙️ {g.name} — Settings", color=discord.Color.teal())
    embed.add_field(name="Welcome", value=status(welcome_data))
    embed.add_field(name="Goodbye", value=status(goodbye_data))
    embed.add_field(name="Join Log", value=status(join_logs))
    embed.add_field(name="Auto-role", value=status(autorole_data))
    embed.add_field(name="Starboard", value=status(starboard_data))
    embed.add_field(name="Counting", value=status(counting_data))
    embed.add_field(name="Confessions", value=status(confession_ch))
    embed.add_field(name="Suggestions", value=status(suggestion_ch))
    embed.add_field(name="Level Channel", value=status(level_channel))
    embed.add_field(name="Boost Msg", value=status(boost_data))
    embed.add_field(name="Mod Log", value=status(log_channel_data))
    embed.add_field(name="Mute Role", value=status(muterole_data))
    await ctx.send(embed=embed)


# ── INFO ───────────────────────────────────────────────────────────────────────
@bot.command()
async def membercount(ctx):
    g = ctx.guild
    humans = sum(1 for m in g.members if not m.bot)
    bots = g.member_count - humans
    embed = discord.Embed(title="👥 Member Count", color=discord.Color.blurple())
    embed.add_field(name="Total", value=str(g.member_count))
    embed.add_field(name="Humans", value=str(humans))
    embed.add_field(name="Bots", value=str(bots))
    await ctx.send(embed=embed)


@bot.command()
async def humancount(ctx):
    await ctx.send(f"👤 **{sum(1 for m in ctx.guild.members if not m.bot)}** humans.")


@bot.command()
async def botcount(ctx):
    await ctx.send(f"🤖 **{sum(1 for m in ctx.guild.members if m.bot)}** bots.")


@bot.command()
async def onlinecount(ctx):
    online = sum(1 for m in ctx.guild.members if str(m.status) != "offline" and not m.bot)
    await ctx.send(f"🟢 **{online}** members online.")


@bot.command()
async def statuscount(ctx):
    c = Counter(str(m.status) for m in ctx.guild.members if not m.bot)
    embed = discord.Embed(title="📶 Status Breakdown", color=discord.Color.blurple())
    embed.add_field(name="🟢 Online", value=str(c.get("online", 0)))
    embed.add_field(name="🟡 Idle", value=str(c.get("idle", 0)))
    embed.add_field(name="🔴 DND", value=str(c.get("dnd", 0)))
    embed.add_field(name="⚫ Offline", value=str(c.get("offline", 0)))
    await ctx.send(embed=embed)


@bot.command()
async def botstats(ctx):
    delta = datetime.datetime.utcnow() - BOT_START
    h, r = divmod(int(delta.total_seconds()), 3600)
    m, s = divmod(r, 60)
    embed = discord.Embed(title="🤖 Bot Statistics", color=discord.Color.blurple())
    embed.add_field(name="Servers", value=str(len(bot.guilds)))
    embed.add_field(name="Users", value=str(len(set(bot.get_all_members()))))
    embed.add_field(name="Commands", value=str(len(bot.commands)))
    embed.add_field(name="Latency", value=f"{round(bot.latency * 1000)}ms")
    embed.add_field(name="Uptime", value=f"{h}h {m}m {s}s")
    embed.add_field(name="Library", value=f"discord.py {discord.__version__}")
    await ctx.send(embed=embed)


@bot.command()
async def rolecount(ctx):
    await ctx.send(f"🎭 This server has **{len(ctx.guild.roles) - 1}** roles.")


@bot.command()
async def rolelist(ctx):
    roles = [r.mention for r in reversed(ctx.guild.roles) if r.name != "@everyone"]
    embed = discord.Embed(title="🎭 Roles", description=" ".join(roles[:50]) or "None", color=discord.Color.blurple())
    embed.set_footer(text=f"Total: {len(roles)}")
    await ctx.send(embed=embed)


@bot.command()
async def biggestrole(ctx):
    roles = [r for r in ctx.guild.roles if r.name != "@everyone"]
    if not roles:
        await ctx.send("❌ No roles.")
        return
    r = max(roles, key=lambda x: len(x.members))
    await ctx.send(f"📈 Most-populated role: **{r.name}** ({len(r.members)} members).")


@bot.command()
async def smallestrole(ctx):
    roles = [r for r in ctx.guild.roles if r.name != "@everyone"]
    if not roles:
        await ctx.send("❌ No roles.")
        return
    r = min(roles, key=lambda x: len(x.members))
    await ctx.send(f"📉 Least-populated role: **{r.name}** ({len(r.members)} members).")


@bot.command()
async def emptyroles(ctx):
    empties = [r.name for r in ctx.guild.roles if r.name != "@everyone" and len(r.members) == 0]
    await ctx.send(embed=discord.Embed(title="🫥 Empty Roles", description=", ".join(empties) or "None", color=discord.Color.greyple()))


@bot.command()
async def norole(ctx):
    members = [m for m in ctx.guild.members if len(m.roles) == 1 and not m.bot]
    await ctx.send(f"🚫 **{len(members)}** members have no role: " + ", ".join(m.display_name for m in members[:15]))


@bot.command()
async def hasrole(ctx, member: discord.Member, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    has = role in member.roles
    await ctx.send(f"{'✅' if has else '❌'} **{member.display_name}** {'has' if has else 'does not have'} **{role.name}**.")


@bot.command()
async def toprole(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"🎖️ **{member.display_name}**'s top role: {member.top_role.mention}")


@bot.command()
async def colorof(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"🎨 **{member.display_name}**'s color: **{member.color}**")


@bot.command()
async def inrole(ctx, *, role_name):
    role = discord.utils.get(ctx.guild.roles, name=role_name)
    if not role:
        await ctx.send("❌ Role not found.")
        return
    members = [m.display_name for m in role.members]
    embed = discord.Embed(title=f"🎭 Members in {role.name}",
                          description=", ".join(members[:50]) or "None", color=role.color)
    embed.set_footer(text=f"Total: {len(members)}")
    await ctx.send(embed=embed)


@bot.command()
async def channelcount(ctx):
    g = ctx.guild
    embed = discord.Embed(title="📚 Channel Count", color=discord.Color.blurple())
    embed.add_field(name="Text", value=str(len(g.text_channels)))
    embed.add_field(name="Voice", value=str(len(g.voice_channels)))
    embed.add_field(name="Categories", value=str(len(g.categories)))
    await ctx.send(embed=embed)


@bot.command()
async def textchannels(ctx):
    chs = [c.mention for c in ctx.guild.text_channels]
    await ctx.send(embed=discord.Embed(title="📝 Text Channels", description=" ".join(chs[:50]), color=discord.Color.blurple()))


@bot.command()
async def voicechannels(ctx):
    chs = [c.name for c in ctx.guild.voice_channels]
    await ctx.send(embed=discord.Embed(title="🔊 Voice Channels", description=", ".join(chs) or "None", color=discord.Color.blurple()))


@bot.command()
async def categories(ctx):
    cats = [c.name for c in ctx.guild.categories]
    await ctx.send(embed=discord.Embed(title="📂 Categories", description=", ".join(cats) or "None", color=discord.Color.blurple()))


@bot.command()
async def channelid(ctx, channel: discord.TextChannel = None):
    channel = channel or ctx.channel
    await ctx.send(f"🆔 {channel.mention} → `{channel.id}`")


@bot.command()
async def emojilist(ctx):
    emojis = [str(e) for e in ctx.guild.emojis]
    if not emojis:
        await ctx.send("📭 No custom emojis.")
        return
    await ctx.send(embed=discord.Embed(title="😀 Server Emojis", description=" ".join(emojis[:50]), color=discord.Color.blurple()))


@bot.command()
async def emojicount(ctx):
    animated = sum(1 for e in ctx.guild.emojis if e.animated)
    await ctx.send(f"😀 **{len(ctx.guild.emojis)}** emojis ({animated} animated).")


@bot.command()
async def stickers(ctx):
    s = [st.name for st in ctx.guild.stickers]
    await ctx.send(embed=discord.Embed(title="🏷️ Stickers", description=", ".join(s) or "None", color=discord.Color.blurple()))


@bot.command()
async def stickercount(ctx):
    await ctx.send(f"🏷️ **{len(ctx.guild.stickers)}** stickers.")


@bot.command()
async def admins(ctx):
    admins = [m.display_name for m in ctx.guild.members if m.guild_permissions.administrator and not m.bot]
    await ctx.send(embed=discord.Embed(title="👑 Admins", description=", ".join(admins) or "None", color=discord.Color.red()))


@bot.command()
async def mods(ctx):
    mods = [m.display_name for m in ctx.guild.members
            if m.guild_permissions.kick_members and not m.guild_permissions.administrator and not m.bot]
    await ctx.send(embed=discord.Embed(title="🛡️ Moderators", description=", ".join(mods) or "None", color=discord.Color.orange()))


@bot.command()
async def bots(ctx):
    bot_list = [m.display_name for m in ctx.guild.members if m.bot]
    await ctx.send(embed=discord.Embed(title="🤖 Bots", description=", ".join(bot_list) or "None", color=discord.Color.blurple()))


@bot.command()
async def owner(ctx):
    await ctx.send(f"👑 Server owner: **{ctx.guild.owner}**")


@bot.command()
async def serverage(ctx):
    days = (datetime.datetime.now(datetime.timezone.utc) - ctx.guild.created_at).days
    await ctx.send(f"📅 **{ctx.guild.name}** is **{days}** days old (created {ctx.guild.created_at.strftime('%Y-%m-%d')}).")


@bot.command()
async def servericon(ctx):
    if ctx.guild.icon:
        embed = discord.Embed(title=f"🖼️ {ctx.guild.name} Icon", color=discord.Color.blurple())
        embed.set_image(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This server has no icon.")


@bot.command()
async def serverbanner(ctx):
    if ctx.guild.banner:
        embed = discord.Embed(title=f"🖼️ {ctx.guild.name} Banner", color=discord.Color.blurple())
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)
    else:
        await ctx.send("❌ This server has no banner.")


@bot.command()
async def vanity(ctx):
    if "VANITY_URL" in ctx.guild.features:
        try:
            inv = await ctx.guild.vanity_invite()
            await ctx.send(f"🔗 Vanity invite: `{inv.code}`")
            return
        except Exception:
            pass
    await ctx.send("❌ This server has no vanity URL.")


@bot.command()
async def features(ctx):
    feats = ctx.guild.features
    await ctx.send(embed=discord.Embed(title="✨ Guild Features",
                   description=", ".join(f.replace("_", " ").title() for f in feats) or "None", color=discord.Color.blurple()))


@bot.command()
async def verificationlevel(ctx):
    await ctx.send(f"🔐 Verification level: **{ctx.guild.verification_level}**")


@bot.command()
async def afkchannel(ctx):
    ch = ctx.guild.afk_channel
    await ctx.send(f"💤 AFK channel: **{ch.name if ch else 'None'}** (timeout {ctx.guild.afk_timeout // 60}m).")


@bot.command()
async def systemchannel(ctx):
    ch = ctx.guild.system_channel
    await ctx.send(f"📨 System channel: {ch.mention if ch else 'None'}")


@bot.command()
async def boostcount(ctx):
    await ctx.send(f"🚀 **{ctx.guild.premium_subscription_count}** boosts.")


@bot.command()
async def boostlevel(ctx):
    await ctx.send(f"🚀 Boost tier: **{ctx.guild.premium_tier}**")


@bot.command()
async def boosters(ctx):
    bs = [m.display_name for m in ctx.guild.premium_subscribers]
    await ctx.send(embed=discord.Embed(title="🚀 Boosters", description=", ".join(bs) or "None", color=discord.Color.magenta()))


@bot.command()
async def oldest(ctx):
    members = sorted([m for m in ctx.guild.members if not m.bot], key=lambda m: m.created_at)[:10]
    lines = [f"**{m.display_name}** — {m.created_at.strftime('%Y-%m-%d')}" for m in members]
    await ctx.send(embed=discord.Embed(title="📜 Oldest Accounts", description="\n".join(lines), color=discord.Color.blurple()))


@bot.command()
async def newest(ctx):
    members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at, reverse=True)[:10]
    lines = [f"**{m.display_name}** — {m.joined_at.strftime('%Y-%m-%d')}" for m in members]
    await ctx.send(embed=discord.Embed(title="🆕 Newest Members", description="\n".join(lines), color=discord.Color.green()))


@bot.command()
async def firstjoined(ctx):
    members = [m for m in ctx.guild.members if m.joined_at]
    if not members:
        await ctx.send("❌ No data.")
        return
    m = min(members, key=lambda x: x.joined_at)
    await ctx.send(f"🏅 First to join: **{m.display_name}** on {m.joined_at.strftime('%Y-%m-%d')}.")


@bot.command()
async def accountage(ctx, member: discord.Member = None):
    member = member or ctx.author
    days = (datetime.datetime.now(datetime.timezone.utc) - member.created_at).days
    await ctx.send(f"📅 **{member.display_name}**'s account is **{days}** days old.")


@bot.command()
async def joinposition(ctx, member: discord.Member = None):
    member = member or ctx.author
    members = sorted([m for m in ctx.guild.members if m.joined_at], key=lambda m: m.joined_at)
    try:
        pos = members.index(member) + 1
        await ctx.send(f"🔢 **{member.display_name}** was member **#{pos}** to join.")
    except ValueError:
        await ctx.send("❌ Could not determine join position.")


@bot.command()
async def joinedat(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"📥 **{member.display_name}** joined on **{member.joined_at.strftime('%Y-%m-%d %H:%M') if member.joined_at else 'Unknown'}**.")


@bot.command()
async def createdat(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"🗓️ **{member.display_name}**'s account was created on **{member.created_at.strftime('%Y-%m-%d')}**.")


@bot.command()
async def avatarurl(ctx, member: discord.Member = None):
    member = member or ctx.author
    await ctx.send(f"🖼️ {member.display_avatar.url}")


@bot.command()
async def bannerurl(ctx, member: discord.Member = None):
    member = member or ctx.author
    user = await bot.fetch_user(member.id)
    await ctx.send(f"🖼️ {user.banner.url if user.banner else 'No banner.'}")


@bot.command()
async def invites(ctx, member: discord.Member = None):
    member = member or ctx.author
    try:
        all_invites = await ctx.guild.invites()
        total = sum(i.uses for i in all_invites if i.inviter and i.inviter.id == member.id)
        await ctx.send(f"📨 **{member.display_name}** has **{total}** invites.")
    except discord.Forbidden:
        await ctx.send("❌ I need 'Manage Server' to view invites.")


# ── REPLY (mod utility) ─────────────────────────────────────────────────────────
@bot.command()
@commands.has_permissions(manage_messages=True)
async def rsp(ctx, message_id: int, *, response):
    try:
        msg = await ctx.channel.fetch_message(message_id)
        await msg.reply(response)
        await ctx.message.delete()
    except Exception:
        await ctx.send("❌ Could not reply to that message.")


# ── RUN ────────────────────────────────────────────────────────────────────────
bot.run(os.getenv("DISCORD_TOKEN"))
