import logging

logger = logging.getLogger("Core.NickServ")

class Plugin(object):
  _name_ = "NickServ"
  _author_ = "Fabian Schlager"
  _description_ = "Handles NickServ authentication"
  _help_ = "NickServ - This plugin handles authentication with NickServ. No commands are available."

  def __init__(self, plugin):
    self.plugin = plugin

    self.plugin.add_event_handler("PRIVNOTICE", self.privnotice_handler)

  def privnotice_handler(self, conn, data):
    nick = data.source.nick

    # only accept NickServ notices
    if nick.lower() != "nickserv":
      return

    # no NickServ password set means the nick isn't registered
    if not self.plugin.get_config_value("password"):
      logger.info("No NickServ password specified, exiting ...")
      return

    # extract message from arguments, strip and lower
    msg = data.arguments[0].split(":", 1)[0].strip().lower()

    # check for typical NickServ responses, kinda dirty
    if "this nickname is registered." in msg:
      logger.info("Identifying with NickServ ...")
      conn.privmsg("NickServ", "identify %s" % (self.plugin.get_config_value("password")))
    elif "you are now identified" in msg:
      logger.info("Succesfully registered!")
    elif "invalid password" in msg:
      logger.warning("Could not identify with NickServ!")
    else:
      logger.info("Unknown message from NickServ: '%s'" % (msg))

