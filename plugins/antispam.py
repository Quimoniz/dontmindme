import time
import logging

MIN_SECONDS_BETWEEN_MESSAGES = 4  # minimal delay in seconds two messages should have
WEBCHAT_MULTIPLIER = 1.5          # additional penalty for webchat users
MAX_FLOOD_SCORE = 15              # maximum score a client can reach before being punished

logger = logging.getLogger("Core.AntiSpam")

class AntiSpamData(object):
  flood_score = 0
  last_message_time = 0
  last_message = ""
  similar_message_count = 0
  flooding = False
  penalty_count = 0
  uses_webchat = False

class Plugin(object):
  _name_ = "AntiSpam"
  _author_ = "Fabian Schlager"
  _description_ = "Checks for spam in any of the bot's channels."

  def __init__(self, plugin):
    self.plugin = plugin
    self.active = True

    self.plugin.add_command_handler("!whitelist", self.whitelist_handler)
    self.plugin.add_command_handler("!quiet", self.quiet_handler)
    self.plugin.add_command_handler("!unquiet", self.unquiet_handler)
    self.plugin.add_command_handler("!antispam", self.antispam_handler)

    self.plugin.add_event_handler("PUBMSG", self.pubmsg_handler)

    self.whitelist = set()
    if self.plugin.get_config_value("whitelist"):
      self.whitelist = set([x.strip() for x in self.plugin.get_config_value("whitelist").split(",")])
      logger.info("Loaded whitelist from config file: %s" % (', '.join(self.whitelist)))

  def antispam_handler(self, conn, params, data):
    nick = data.source.nick

    if len(params) != 1:
      conn.privmsg(nick, "!antispam on|off - Activate/Deactivate the automatic spam control")
      return

    if params[0].lower() == "on":
      self.active = True
      conn.privmsg(nick, "Activated automatic flood protection!")
    elif params[0].lower() == "off":
      self.active = False
      conn.privmsg(nick, "Deactivated automatic flood protection!")
    else:
      conn.privmsg("Use 'on' or 'off'!")

  def quiet_handler(self, conn, params, data):
    nick = data.source.nick

    if len(params) != 2:
      conn.privmsg(nick, "!quiet <channel> <hostmask> - Silence a user in a channel")
      return
   
    conn.privmsg(nick, "Trying to quiet %s ..." % (params[1]))
    conn.privmsg("ChanServ", "QUIET " + params[0] + " " + params[1])

  def unquiet_handler(self, conn, params, data):
    nick = data.source.nick

    if len(params) != 2:
      conn.privmsg(nick, "!unquiet <channel> <hostmask> - Let's a previously punished user talk again")
      return
   
    conn.privmsg(nick, "Trying to unquiet %s ..." % (params[1]))
    conn.privmsg("ChanServ", "UNQUIET " + params[0] + " " + params[1])

  def whitelist_handler(self, conn, params, data):
    nick = data.source.nick

    if len(params) < 1:
      conn.privmsg(nick, "!whitelist add <nick>|del <nick>|list - Manage the bot's whitelist")
      return
    
    if params[0] == "list":
      if len(self.whitelist):
        conn.privmsg(nick, "Whitelist: " + ', '.join(self.whitelist))
      else:
        conn.privmsg(nick, "Whitelist is empty")
      return

    if len(params) < 2:
      return
    
    target = params[1]
      
    if params[0] == "add":
      self.whitelist.add(target)
      conn.privmsg(nick, "User '%s' added to whitelist" % (target))
    elif params[0] == "del":
      if target in self.whitelist:
        self.whitelist.remove(target)
        conn.privmsg(nick, "User '%s' removed from whitelist" % (target))
      else:
        conn.privmsg(nick, "User '%s' not on whitelist" % (target))

  def pubmsg_handler(self, conn, data):
    channel_name = data.target
    channel = self.plugin.get_bot().get_channel(channel_name)
    
    user = channel.get_user(data.source.nick)
    message = data.arguments[0].split(":", 1)

    # inject anti spam data into new users
    if not hasattr(user, "plugin_antispam"):
      user.plugin_antispam = {}
      
    if channel_name not in user.plugin_antispam:
      user.plugin_antispam[channel_name] = AntiSpamData()

      # check if users is connected via freenode webchat
      if user.get_host().startswith("gateway/web"):
        user.plugin_antispam[channel_name].uses_webchat = True

    if user.nick in self.whitelist:
      return

    self.update(user.plugin_antispam[channel_name], message)

    if user.plugin_antispam[channel_name].flooding:
      logger.info("User '%s' (%s, %s) is spamming!" % (user.get_nick(), user.get_host(), channel_name))

      if self.active:
        conn.privmsg("ChanServ", "QUIET " + channel_name + " " + user.get_nick())

      user.plugin_antispam[channel_name].flooding = False

  def update(self, user, message):
    # a pause of a few seconds between messages keeps flood_score at 0
    msg_length = len(message)
    min_message_delay = MIN_SECONDS_BETWEEN_MESSAGES + (user.uses_webchat*2)
    user.flood_score += (min_message_delay - (time.time() - user.last_message_time))

    # additional penalty for long lines
    user.flood_score += min(11, (msg_length/80)**1.7)
    user.last_message_time = time.time()

    if user.flood_score < 0:
      user.flood_score = 0

    # repeating messages increases flood_score
    # this string comparison could be implemented as a levenshtein ratio
    # to make it more robust against small text changes
    if message == user.last_message:
      user.similar_message_count += 1
      user.flood_score *= (user.similar_message_count)
    else:
      user.similar_message_count = 0
    
    user.last_message = message

    # webchat users are more likely to be evil
    # proven by several studies
    if user.uses_webchat:
      user.flood_score *= WEBCHAT_MULTIPLIER

    # TODO check for nazi scum catchphrases
    # TODO Decrease flood score for registered users

    # flood_score threshhold
    if user.flood_score >= MAX_FLOOD_SCORE:
      user.flooding = True
      user.penalty_count += 1
      
      # reset flood_score once a user is blamed
      # to avoid keeping a user in jail repeatedly
      user.flood_score = 0
    else:
      user.flooding = False




