import discord
import logging
import asyncio
import datetime

from typing import Union, Optional

from redbot.core import commands, Config, checks
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.menus import menu, DEFAULT_CONTROLS

from .errors import Destiny2APIError, Destiny2MissingManifest
from .converter import DestinyActivity
from .api import DestinyAPI


BASE_URL = "https://www.bungie.net/Platform"
IMAGE_URL = "https://www.bungie.net"
AUTH_URL = "https://www.bungie.net/en/oauth/authorize"
TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
_ = Translator("Destiny", __file__)
log = logging.getLogger("red.Destiny")


@cog_i18n(_)
class Destiny(DestinyAPI, commands.Cog):
    """
        Get information from the Destiny 2 API
    """

    __version__ = "1.1.1"
    __author__ = "TrustyJAID"

    def __init__(self, bot):
        self.bot = bot
        default_global = {
            "api_token": {"api_key": "", "client_id": "", "client_secret": ""},
            "manifest_version": "",
        }
        default_user = {"oauth": {}, "account": {}}
        self.config = Config.get_conf(self, 35689771456)
        self.config.register_global(**default_global, force_registration=True)
        self.config.register_user(**default_user, force_registration=True)
        self.throttle: float = 0
        # self.manifest_download_start = bot.loop.create_task(self.get_manifest())

    @staticmethod
    def humanize_timedelta(
        *, timedelta: Optional[datetime.timedelta] = None, seconds: Optional[int] = None
    ) -> str:
        """
        Get a human timedelta representation

        Only here until available in Core Red from PR
        https://github.com/Cog-Creators/Red-DiscordBot/pull/2412
        """

        try:
            obj = seconds or timedelta.total_seconds()
        except AttributeError:
            raise ValueError("You must provide either a timedelta or a number of seconds")

        seconds = int(obj)
        periods = [
            (_("year"), _("years"), 60 * 60 * 24 * 365),
            (_("month"), _("months"), 60 * 60 * 24 * 30),
            (_("day"), _("days"), 60 * 60 * 24),
            (_("hour"), _("hours"), 60 * 60),
            (_("minute"), _("minutes"), 60),
            (_("second"), _("seconds"), 1),
        ]

        strings = []
        for period_name, plural_period_name, period_seconds in periods:
            if seconds >= period_seconds:
                period_value, seconds = divmod(seconds, period_seconds)
                if period_value == 0:
                    continue
                unit = plural_period_name if period_value > 1 else period_name
                strings.append(f"{period_value} {unit}")

        return ", ".join(strings)

    @commands.group()
    async def destiny(self, ctx):
        """Get information from the Destiny 2 API"""
        pass

    @destiny.group(aliases=["s"])
    async def search(self, ctx: commands.Context):
        """
            Search for a destiny item, vendor, record, etc.
        """
        pass

    @search.command(aliases=["item"])
    @commands.bot_has_permissions(embed_links=True)
    async def items(self, ctx: commands.Context, *, search: str):
        """
            Search for a specific item in Destiny 2
        """
        try:
            items = await self.search_definition("DestinyInventoryItemDefinition", search)
        except Destiny2MissingManifest as e:
            await ctx.send(e)
            return
        if not items:
            await ctx.send(_("`{search}` could not be found.").format(search=search))
            return
        embeds = []
        log.debug(items[0])
        for item in items:
            if not (item["equippable"]):
                continue
            embed = discord.Embed()
            embed.description = item["displayProperties"]["description"]
            embed.title = item["itemTypeAndTierDisplayName"]
            name = item["displayProperties"]["name"]
            icon_url = IMAGE_URL + item["displayProperties"]["icon"]
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=icon_url)
            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def user(self, ctx: commands.Context, user: discord.Member = None):
        """
            Display a menu of your basic characters info
            `[user]` A member on the server who has setup their account on this bot.
        """
        if not await self.has_oauth(ctx, user):
            return
        if not user:
            user = ctx.author
        try:
            chars = await self.get_characters(user)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            info = ""
            race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
            gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
            info += "{race} {gender} {char_class} ".format(
                race=race[0]["displayProperties"]["name"],
                gender=gender[0]["displayProperties"]["name"],
                char_class=char_class[0]["displayProperties"]["name"],
            )
            titles = ""
            if "titleRecordHash" in char:
                # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
                char_title = await self.get_definition(
                    "DestinyRecordDefinition", [char["titleRecordHash"]]
                )
                title_info = "**{title_name}**\n{title_desc}\n"
                for t in char_title:
                    try:
                        title_name = t["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                        title_desc = t["displayProperties"]["description"]
                        titles += title_info.format(title_name=title_name, title_desc=title_desc)
                    except:
                        pass
            embed = discord.Embed(title=info)
            embed.set_author(name=user.display_name, icon_url=user.avatar_url)
            if "emblemPath" in char:
                embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
            items = chars["characterEquipment"]["data"][char_id]["items"]
            # log.debug(data)
            level = char["baseCharacterLevel"]
            light = char["light"]
            level_str = _("Level: **{level}**  \nLight: **{light}**").format(
                level=level, light=light
            )
            embed.description = level_str
            embed = await self.get_char_colour(embed, char)
            if titles:
                embed.add_field(name=_("Titles"), value=titles)
            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command(aliases=["xûr"])
    @commands.bot_has_permissions(embed_links=True)
    async def xur(self, ctx: commands.Context, full: bool = False):
        """
            Display a menu of Xûr's current wares

            `[full=False]` Show perk definition on Xûr's current wares
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            try:
                xur = await self.get_vendor(ctx.author, char_id, "2190858386")
                xur_def = await self.get_definition("DestinyVendorDefinition", ["2190858386"])
            except Destiny2APIError:
                log.error("I can't seem to see Xûr at the moment")
                today = datetime.datetime.utcnow()
                friday = today.replace(hour=17, minute=0, second=0) + datetime.timedelta(
                    (4 - today.weekday()) % 7
                )
                next_xur = self.humanize_timedelta(timedelta=(friday - today))
                await ctx.send(
                    _("Xûr's not around, come back in {next_xur}.").format(next_xur=next_xur)
                )
                return
            break
        items = [v["itemHash"] for k, v in xur["sales"]["data"].items()]
        data = await self.get_definition("DestinyInventoryItemDefinition", items)
        embeds = []
        embed = discord.Embed(
            colour=discord.Colour.red(), description=xur_def[0]["displayProperties"]["description"]
        )
        embed.set_thumbnail(
            url=IMAGE_URL + xur_def[0]["displayProperties"]["largeTransparentIcon"]
        )
        embed.set_author(name="Xûr's current wares")
        for item in data:
            if not (item["equippable"]):
                continue
            perk_hashes = [
                str(p["singleInitialItemHash"]) for p in item["sockets"]["socketEntries"]
            ]
            perk_data = await self.get_definition("DestinyInventoryItemDefinition", perk_hashes)
            perks = ""

            for perk in perk_data:
                properties = perk["displayProperties"]
                if "Common" in perk["itemTypeAndTierDisplayName"]:
                    continue
                if (
                    properties["name"] == "Empty Mod Socket"
                    or properties["name"] == "Default Ornament"
                ):
                    continue
                if "name" in properties and "description" in properties:
                    if full:
                        perks += "**{0}** - {1}\n".format(
                            properties["name"], properties["description"]
                        )
                    else:
                        perks += "- **{0}**\n".format(properties["name"])
            msg = (
                item["itemTypeAndTierDisplayName"]
                + "\n"
                + (item["displayProperties"]["description"] + "\n" if full else "")
                + perks
            )
            embed.add_field(name="**__" + item["displayProperties"]["name"] + "__**\n", value=msg)
        await ctx.send(embed=embed)
        # await ctx.tick()
        # await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True)
    async def eververse(self, ctx: commands.Context):
        """
            Display items available on the eververse right now
        """
        if not await self.has_oauth(ctx):
            return
        try:
            chars = await self.get_characters(ctx.author)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            log.debug(char_id)
            try:
                eververse = await self.get_vendor(ctx.author, char_id, "3361454721")
            except Destiny2APIError as e:
                log.error("I can't seem to see the eververse at the moment", exc_info=True)
                await ctx.send(_("I can't access the eververse at the moment."))
                return
            break
        items = [v["itemHash"] for k, v in eververse["sales"]["data"].items()]
        data = await self.get_definition("DestinyInventoryItemDefinition", items)
        embeds = []
        for item in data:
            if not (item["equippable"]):
                continue
            embed = discord.Embed()
            embed.description = item["displayProperties"]["description"]
            embed.title = item["itemTypeAndTierDisplayName"]
            name = item["displayProperties"]["name"]
            icon_url = IMAGE_URL + item["displayProperties"]["icon"]
            embed.set_author(name=name, icon_url=icon_url)
            embed.set_thumbnail(url=icon_url)
            embeds.append(embed)

        # await ctx.tick()
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def loadout(
        self, ctx: commands.Context, full: Optional[bool] = False, user: discord.Member = None
    ):
        """
            Display a menu of each characters equipped weapons and their info

            `[full=False]` Display full information about weapons equipped.
            `[user]` A member on the server who has setup their account on this bot.
        """
        if not await self.has_oauth(ctx, user):
            return
        if not user:
            user = ctx.author
        try:
            chars = await self.get_characters(user)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            info = ""
            race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
            gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
            info += "{race} {gender} {char_class} ".format(
                race=race[0]["displayProperties"]["name"],
                gender=gender[0]["displayProperties"]["name"],
                char_class=char_class[0]["displayProperties"]["name"],
            )
            titles = ""
            if "titleRecordHash" in char:
                # TODO: Add fetch for Destiny.Definitions.Records.DestinyRecordDefinition
                char_title = await self.get_definition(
                    "DestinyRecordDefinition", [char["titleRecordHash"]]
                )
                title_info = "**{title_name}**\n{title_desc}\n"
                for t in char_title:
                    try:
                        title_name = t["titleInfo"]["titlesByGenderHash"][str(char["genderHash"])]
                        title_desc = t["displayProperties"]["description"]
                        titles += title_info.format(title_name=title_name, title_desc=title_desc)
                    except:
                        pass
                log.debug("User has a title")
                pass
            embed = discord.Embed(title=info)
            embed.set_author(name=user.display_name, icon_url=user.avatar_url)
            if "emblemPath" in char:
                embed.set_thumbnail(url=IMAGE_URL + char["emblemPath"])
            if titles:
                embed.add_field(name=_("Titles"), value=titles)
            char_items = chars["characterEquipment"]["data"][char_id]["items"]
            item_list = [i["itemHash"] for i in char_items]
            # log.debug(item_list)
            items = await self.get_definition("DestinyInventoryItemDefinition", item_list)
            # log.debug(items)
            for data in items:
                # log.debug(data)
                for item in char_items:
                    # log.debug(item)
                    if data["hash"] == item["itemHash"]:
                        instance_id = item["itemInstanceId"]
                item_instance = chars["itemComponents"]["instances"]["data"][instance_id]
                if not item_instance["isEquipped"]:
                    continue

                if not (data["equippable"] and data["itemType"] == 3):
                    continue
                name = data["displayProperties"]["name"]
                desc = data["displayProperties"]["description"]
                item_type = data["itemTypeAndTierDisplayName"]
                try:
                    light = item_instance["primaryStat"]["value"]
                except KeyError:
                    light = ""
                perk_list = chars["itemComponents"]["perks"]["data"][instance_id]["perks"]
                perk_hashes = [p["perkHash"] for p in perk_list]
                perk_data = await self.get_definition("DestinySandboxPerkDefinition", perk_hashes)
                perks = ""
                for perk in perk_data:
                    properties = perk["displayProperties"]
                    if "name" in properties and "description" in properties:
                        if full:
                            perks += "**{0}** - {1}\n".format(
                                properties["name"], properties["description"]
                            )
                        else:
                            perks += "- **{0}**\n".format(properties["name"])

                value = f"**{light}** {item_type}\n{perks}"
                embed.add_field(name=name, value=value, inline=True)
            # log.debug(data)
            level = char["baseCharacterLevel"]
            light = char["light"]
            level_str = _("Level: **{level}**  \nLight: **{light}**").format(
                level=level, light=light
            )
            embed.description = level_str
            embed = await self.get_char_colour(embed, char)

            embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def gambit(self, ctx):
        """
            Display a menu of past gambit matches
        """
        msg = ctx.message
        msg.content = f"{ctx.prefix}destiny history gambit"
        ctx.bot.dispatch("message", msg)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def pvp(self, ctx):
        """
            Display a menu of past pvp matches
        """
        msg = ctx.message
        msg.content = f"{ctx.prefix}destiny history pvp"
        ctx.bot.dispatch("message", msg)

    @destiny.command(aliases=["raids"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def raid(self, ctx):
        """
            Display a menu of past RAIDS
        """
        msg = ctx.message
        msg.content = f"{ctx.prefix}destiny history raid"
        ctx.bot.dispatch("message", msg)

    @destiny.command(aliases=["qp"])
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def quickplay(self, ctx):
        """
            Display a menu of past quickplay matches
        """
        msg = ctx.message
        msg.content = f"{ctx.prefix}destiny history pvpquickplay"
        ctx.bot.dispatch("message", msg)

    @destiny.command()
    @commands.bot_has_permissions(embed_links=True, add_reactions=True)
    async def history(self, ctx: commands.Context, activity: DestinyActivity):
        """
            Display a meny of each characters last 5 activities

            `<activity>` The activity type to display stats on available types include:
            all, story, strike, raid, allpvp, patrol, allpve, control, clash, 
            crimsondoubles, nightfall, heroicnightfall, allstrikes, ironbanner, allmayhem, 
            supremacy, privatematchesall, survival, countdown, trialsofthenine, social, 
            trialscountdown, trialssurvival, ironbannercontrol, ironbannerclash, 
            ironbannersupremacy, scorednightfall, scoredheroicnightfall, rumble, alldoubles, 
            doubles, privatematchesclash, privatematchescontrol, privatematchessupremacy, 
            privatematchescountdown, privatematchessurvival, privatematchesmayhem, 
            privatematchesrumble, heroicadventure, showdown, lockdown, scorched, 
            scorchedteam, gambit, allpvecompetitive, breakthrough, blackarmoryrun, 
            salvage, ironbannersalvage, pvpcompetitive, pvpquickplay, clashquickplay, 
            clashcompetitive, controlquickplay, and controlcompetitive
        """
        if not await self.has_oauth(ctx):
            return
        user = ctx.author
        try:
            chars = await self.get_characters(user)
        except Destiny2APIError as e:
            # log.debug(e)
            msg = _("I can't seem to find your Destiny profile.")
            await ctx.send(msg)
            return
        RAID = {
            "assists": _("Assists"),
            "kills": _("Kills"),
            "deaths": _("Deaths"),
            "opponentsDefeated": _("Opponents Defeated"),
            "efficiency": _("Efficiency"),
            "killsDeathsRatio": _("KDR"),
            "killsDeathsAssists": _("KDA"),
            "score": _("Score"),
            "activityDurationSeconds": _("Duration"),
            "playerCount": _("Player Count"),
            "teamScore": _("Team Score"),
            "completed": _("Completed"),
        }
        embeds = []
        for char_id, char in chars["characters"]["data"].items():
            # log.debug(char)
            char_info = ""
            race = await self.get_definition("DestinyRaceDefinition", [char["raceHash"]])
            gender = await self.get_definition("DestinyGenderDefinition", [char["genderHash"]])
            char_class = await self.get_definition("DestinyClassDefinition", [char["classHash"]])
            char_info += "{user} - {race} {gender} {char_class} ".format(
                user=user.display_name,
                race=race[0]["displayProperties"]["name"],
                gender=gender[0]["displayProperties"]["name"],
                char_class=char_class[0]["displayProperties"]["name"],
            )
            try:
                data = await self.get_activity_history(user, char_id, activity)
            except:
                log.error(
                    _(
                        "Something went wrong I couldn't get info on character {char_id} for activity {activity}"
                    ).format(char_id=char_id, activity=activity)
                )
                continue
            if not data:
                continue

            for activities in data["activities"]:
                activity_hash = str(activities["activityDetails"]["directorActivityHash"])
                activity_data = await self.get_definition(
                    "DestinyActivityDefinition", [activity_hash]
                )
                activity_data = activity_data[0]
                info = ""
                embed = discord.Embed(
                    title=activity_data["displayProperties"]["name"],
                    description=activity_data["displayProperties"]["description"],
                )
                date = datetime.datetime.strptime(activities["period"], "%Y-%m-%dT%H:%M:%SZ")
                embed.timestamp = date
                if activity_data["displayProperties"]["hasIcon"]:
                    embed.set_thumbnail(url=IMAGE_URL + activity_data["displayProperties"]["icon"])
                elif activity_data["pgcrImage"] != "/img/misc/missing_icon_d2.png":
                    embed.set_thumbnail(url=IMAGE_URL + activity_data["pgcrImage"])
                embed.set_author(name=char_info, icon_url=user.avatar_url)
                for attr, name in RAID.items():
                    if activities["values"][attr]["basic"]["value"] < 0:
                        continue
                    embed.add_field(
                        name=name, value=str(activities["values"][attr]["basic"]["displayValue"])
                    )
                embed = await self.get_char_colour(embed, char)

                embeds.append(embed)
        await menu(ctx, embeds, DEFAULT_CONTROLS)

    @destiny.command()
    @checks.is_owner()
    @commands.bot_has_permissions(add_reactions=True)
    async def manifest(self, ctx):
        """
            See the current manifest version and optionally re-download it
        """
        version = await self.config.manifest_version()
        if not version:
            version = "Not Downloaded"
        await ctx.send(_("Current manifest version is {version}").format(version=version))
        while True:
            msg = await ctx.send(_("Would you like to re-download the manifest?"))
            await msg.add_reaction("✅")
            await msg.add_reaction("❌")
            check = lambda r, u: u == ctx.author and str(r.emoji) in ["✅", "❌"]
            try:
                react, user = await self.bot.wait_for("reaction_add", check=check, timeout=15)
            except asyncio.TimeoutError:
                await msg.delete()
                break
            if str(react.emoji) == "✅":
                try:
                    await self.get_manifest()
                except:
                    await ctx.send(_("There was an issue downloading the manifest."))
                await msg.delete()
                await ctx.tick()
                break
            else:
                await msg.delete()
                break

    @destiny.command()
    @checks.is_owner()
    async def token(self, ctx, api_key: str, client_id: str, client_secret: str):
        """
        Set the API tokens for Destiny 2's API

        Required information is found at:
        https://www.bungie.net/en/Application 
        select create a new application
        choose **Confidential** OAuth Client type
        Select the scope you would like the bot to have access to
        Set the redirect URL to https://localhost/
        NOTE: It is strongly recommended to use this command in DM
        """
        await self.config.api_token.api_key.set(api_key)
        await self.config.api_token.client_id.set(client_id)
        await self.config.api_token.client_secret.set(client_secret)
        if ctx.channel.permissions_for(ctx.me).manage_messages:
            await ctx.message.delete()
        await ctx.send("Destiny 2 API credentials set!")
