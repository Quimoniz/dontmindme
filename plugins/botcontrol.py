import logging

logger = logging.getLogger("Core.BotControl")

class Plugin(object):
  _name_ = "BotControl"
  _author_ = "Fabian Schlager"
  _description_ = "Basic bot control commands such as !join, !part, ..."

  def __init__(self, plugin):
    self.plugin = plugin

    self.plugin.add_command_handler("!join", self.join_handler)
    self.plugin.add_command_handler("!part", self.part_handler)
    self.plugin.add_command_handler("!nick", self.nick_handler)
    self.plugin.add_command_handler("!channels", self.channels_handler)

  def channels_handler(self, conn, params, data):
    conn.privmsg(data.source.nick, "Current channels: %s" % (", ".join(self.plugin.bot.channels)))

  def join_handler(self, conn, params, data):
    if len(params) != 1:
      conn.privmsg(data.source.nick, "Usage: !join <channel>")
      return
    
    logger.info("Joining channel '%s'" % (params[0]))
    conn.join(params[0])

  def part_handler(self, conn, params, data):
    if len(params) != 1:
      conn.privmsg(data.source.nick, "Usage: !part <channel>")
      return

    logger.info("Parting channel '%s'" % (params[0]))
    conn.part(params[0])

  def nick_handler(self, conn, params, data):
    if len(params) != 1:
      conn.privmsg(data.source.nick, "Usage: !nick <nick>")
      return

    logger.info("Changing nick to '%s'" % (params[0]))
    conn.nick(params[0])
