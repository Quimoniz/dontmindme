#!/usr/bin/env python2.7

import time, datetime
import getpass
import os
import imp
import logging
import ConfigParser
import irc.bot
import irc.strings
import irc.client
from irc.dict import IRCDict

CTCP_VERSION           = "DontMindMe - General Purpose IRC Bot (skyr.at)"

class PluginError(Exception):
  def __init__(self, msg):
    self.msg = msg

  def __str__(self):
    return repr(self.msg)

class BotError(Exception):
  def __init__(self, msg):
    self.msg = msg

  def __str__(self):
    return repr(self.msg)

class User(object):
  def __init__(self, nick, host):
    self.nick = nick
    self.host = host

  def get_nick(self):
    return self.nick

  def get_host(self):
    return self.host

  def get_host(self):
    return self.host

  def set_host(self, host):
    self.host = host
    
class Channel(irc.bot.Channel):
  def __init__(self):
    irc.bot.Channel.__init__(self)
    self.users = IRCDict()
  
  def add_user(self, nick, host):
    irc.bot.Channel.add_user(self, nick)
    self.users[nick] = User(nick, host)

  def remove_user(self, nick):
    irc.bot.Channel.remove_user(self, nick)
    if nick in self.users:
      del self.users[nick]

  def change_nick(self, before, after):
    irc.bot.Channel.change_nick(self, before, after)
    self.users[after] = self.users.pop(before)
    self.users[after].name = after

  def get_user(self, nick):
    if nick in self.users:
      return self.users[nick]
    else:
      return None

# Plugin class
class Plugin(object):
  def __init__(self, bot, name, long_name, author, desc):
    self.bot = bot
    self.name = name
    self.long_name = long_name
    self.author = author
    self.description = desc
    self.command_handler = {}
    self.event_handler = {}
    self.instance = None

  def get_bot(self):
    return self.bot

  def get_description(self):
    return self.description

  def __str__(self):
    return "%s - %s" % (self.long_name, self.author)

  def get_config_value(self, key, default=""):
    try:
      return self.bot.config.get(self.name, key)
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as e:
      return default

  def set_instance(self, instance):
    self.instance = instance

  def add_command_handler(self, command, handler):
    self.command_handler[command] = handler

  def add_event_handler(self, event, handler):
    self.event_handler[event] = handler

  def handle_command(self, conn, command, data):
    self.command_handler[command[0]](conn, command[1:], data)

  def handle_event(self, conn, event, data):
    self.event_handler[event](conn, data)

  def has_command_handler(self, cmd):
    return cmd in self.command_handler

  def has_event_handler(self, event):
    return event in self.event_handler

class FloodBot(irc.bot.SingleServerIRCBot):
  def __init__(self, logger, config, nickname, server, port):
    irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.logger             = logger
    self.admins             = set()
    self.plugins            = {}
    self.config             = ConfigParser.ConfigParser()
    self.admin_secret       = ""
    self.autojoin_channels  = []

    if config:
      if config not in self.config.read(config):
        raise BotError("Could not read configuration file '%s'!" % (config))

      self.autoload_plugins()

      if self.config.has_option("core", "channels"):
        self.autojoin_channels = self.config.get("core", "channels").split(",")

      if self.config.has_option("core", "secret"):
        self.admin_secret = self.config.get("core", "secret")

    if len(self.autojoin_channels):
      self.logger.info("Auto joining channels: " + ', '.join(self.autojoin_channels))

  # tries to load the modules specified in the config file
  def autoload_plugins(self):
    try:
      for plugin in self.config.get("core", "plugins").split(","):
        try:
          self.load_plugin(plugin.strip())
        except PluginError, e:
          # silently ignore PluginErrors and try to load the next one
          pass
    except (ConfigParser.NoSectionError, ConfigParser.NoOptionError) as e:
      return

  # checks if a user is a channel op in one of our channels
  def is_user_admin(self, source):
    if source in self.admins:
      return True

    for _, channel in self.channels.items():
      if channel.is_oper(source.nick):
        return True

    return False

  # plugin management
  def get_plugin_list(self):
    return [x[:-3] for x in os.listdir("plugins") if os.path.splitext(x)[1].lower() == ".py" and x != "__init__.py"]

  # dynamically imports a python file
  def load_plugin(self, plugin):
    py_mod = imp.load_source(plugin, "plugins/%s.py" % (plugin))
    py_mod.User = User

    try:
      plugin_class = py_mod.Plugin
      self.plugins[plugin] = Plugin(self, plugin, plugin_class._name_, plugin_class._author_, plugin_class._description_)
      self.plugins[plugin].set_instance(plugin_class(self.plugins[plugin]))
    except AttributeError, e:
      if plugin in self.plugins:
        del self.plugins[plugin]
      self.logger.exception("Error loading plugin '%s': " % (plugin))
      raise PluginError("No class 'Plugin' found in plugin '%s'!" % (plugin,))
    
    self.logger.info("Successfully loaded plugin '%s'!" % (plugin))

  def unload_plugin(self, plugin):
    self.logger.info("Unloading plugin '%s'." % (plugin))
    del self.plugins[plugin]

  def plugin_handle_command(self, conn, cmd, data):
    for name, plugin in self.plugins.items():
      if plugin.has_command_handler(cmd[0]):

        # run this encapsulated in a dirty catch-all try
        # to prevent the bot from crashing when a plugin 
        # is errornous and unload the plugin in case
        try:
          plugin.handle_command(conn, cmd, data)
        except:
          self.logger.exception("Error on running plugin command handler for '%s'!" % (cmd[0]))
          self.unload_plugin(name)
          raise PluginError("Error on running plugin command handler! Unloading plugin ...")

        return True
    return False

  # this method does not return once a fitting handler is found
  # to let more than one plugin handle things
  def plugin_handle_event(self, conn, event, data):
    for name, plugin in self.plugins.items():
      if plugin.has_event_handler(event):
        
        # run this encapsulated in a dirty catch-all try
        # to prevent the bot from crashing when a plugin 
        # is errornous and unload the plugin in case
        try:
          plugin.handle_event(conn, event, data)
        except:
          self.logger.exception("Error on running plugin event handler for '%s'!" % (event))
          self.unload_plugin(name)
          raise PluginError("Error on running plugin command handler! Unloading plugin ...")

    return False

  # small helper function for !plugin load
  def cmd_plugin_load(self, c, nick, plugin):
    try:
      self.load_plugin(plugin)
    except (ImportError, PluginError) as e:
      c.privmsg(nick, "Error loading plugin: %s" % (e,))
    else:
      c.privmsg(nick, "Loaded plugin '%s'!" % (plugin, ))

  def get_channel(self, name):
    return self.channels[name]

  # overwrite this to make use of our own Channel class
  def _on_join(self, c, e):
    ch = e.target
    nick = e.source.nick
    if nick == c.get_nickname():
      self.channels[ch] = Channel()

    self.channels[ch].add_user(nick, e.source.host)

  def _on_namreply(self, c, e):
    # e.arguments[0] == "@" for secret channels,
    #                     "*" for private channels,
    #                     "=" for others (public channels)
    # e.arguments[1] == channel
    # e.arguments[2] == nick list

    ch = e.arguments[1]
    for nick in e.arguments[2].split():
        if nick[0] == "@":
            nick = nick[1:]
            self.channels[ch].set_mode("o", nick)
        elif nick[0] == "+":
            nick = nick[1:]
            self.channels[ch].set_mode("v", nick)

        # there's no hostmask on the NAMES list
        self.channels[ch].add_user(nick, "")

  # automatically append an underscore when the desired nickname is in use
  def on_nicknameinuse(self, c, e):
    c.nick(c.get_nickname() + "_")

  def on_join(self, c, e):
    # run JOIN event
    try:
      self.plugin_handle_event(c, "JOIN", e)
    except PluginError, e:
      return

  def on_part(self, c, e):
    # run PART event
    try:
      self.plugin_handle_event(c, "PART", e)
    except PluginError, e:
      return
  
  def on_pubmsg(self, c, e):
    channel_name = e.target
    
    # ignore queries
    if not irc.client.is_channel(channel_name):
      return

    nick = e.source.nick
    channel = self.channels[channel_name]
    user = channel.get_user(nick)

    # this should actually never happen
    # but it does on servers with specific channel owner mode ("~")
    # this probably is a bug in python-irc
    if user == None:
      self.logger.error("Unknown user: '%s'. I'm scared!" % (nick))
      return

    # when we join a channel, we don't have the host of users already in there
    # so we update this once they say something
    if user.host == "":
      user.set_host(e.source.host)
    
    # run PUBMSG event
    try:
      self.plugin_handle_event(c, "PUBMSG", e)
    except PluginError, e:
      return

  def on_privnotice(self, c, e):
    # run PRIVNOTICE event
    try:
      self.plugin_handle_event(c, "PRIVNOTICE", e)
    except PluginError, e:
      return

  def on_privmsg(self, c, e):
    nick = e.source.nick

    # extract message from arguments, strip
    msg = e.arguments[0].split(":", 1)[0].strip()
   
    # commands have to start with '!'
    if not msg.startswith("!"):
      return

    # allow authorization of non-op admins
    if msg.startswith("!secret"):
      if " " not in msg:
        return

      secret = msg.split(" ")[1]

      if self.admin_secret and secret == self.admin_secret:
        self.admins.add(e.source)
        self.logger.info("Authorized '" + e.source + "' as admin!")
        c.privmsg(nick, "You have been authorized!")
      else:
        self.logger.warning("Unsuccessful login attempt by '" + nick + "' (" + e.source + "): '" + msg + "'")
      
      return

    # only allow admins to issue commands
    # log unauthorized tries
    if not self.is_user_admin(e.source):
      self.logger.warning("Unauthorized command by user '" + nick + "' (" + e.source + ")")
      return False
    
    self.logger.info("User '" + nick + "' (" + e.source + ") issued command: '" + msg + "'")

    cmd = msg.split(" ")

    # only lower the first part as this is the command
    cmd[0] = cmd[0].lower()

    if cmd[0] == "!plugin":
      if len(cmd) < 2:
        c.privmsg(nick, "!plugin load <name>|unload <name>|info <name|list - Manage the bot's plugins")
        return

      if len(cmd) == 2:
        if cmd[1] == "list":
          plugin_list = [x if x not in self.plugins else x + "*" for x in self.get_plugin_list() ]
          c.privmsg(nick, "Plugins: %s" % (', '.join(plugin_list)))
      elif len(cmd) == 3:
        if cmd[1] == "load":
          plugin = cmd[2]
          if plugin in self.plugins:
            c.privmsg(nick, "This plugin is already running.")
            return

          if plugin not in self.get_plugin_list():
            c.privmsg(nick, "No such plugin '%s'!" % (plugin,))
            return

          self.cmd_plugin_load(c, nick, plugin)

        elif cmd[1] == "unload":
          plugin = cmd[2]
          if plugin not in self.plugins:
            c.privmsg(nick, "This plugin is not running.")
            return

          self.unload_plugin(plugin)

        elif cmd[1] == "reload":
          plugin = cmd[2]
          if plugin not in self.plugins:
            c.privmsg(nick, "This plugin is not running.")
            return
         
          self.unload_plugin(plugin)
          self.cmd_plugin_load(c, nick, plugin)

        elif cmd[1] == "info":
          plugin = cmd[2]

          if plugin not in self.plugins:
            c.privmsg(nick, "Plugin has to be running first.")
            return

          c.privmsg(nick, str(self.plugins[plugin]))
          c.privmsg(nick, self.plugins[plugin].get_description())

      return

    # admin management
    elif cmd[0] == "!admin":
      if len(cmd) < 2:
        c.privmsg(nick, "!admin list|remove <hostmask>|purge - Manage administrators")
        return
      
      if len(cmd) == 2:
        if cmd[1] == "list":
          if not len(self.admins):
            c.privmsg(nick, "There are no administrators!")

          for admin in self.admins:
            c.privmsg(nick, admin)
        elif cmd[1] == "purge":
          c.privmsg(nick, "Administrator list purged! Admins will have to log in again next time.")
          c.admins = set()
      elif len(cmd) == 3:
        if cmd[1] == "remove":
          if cmd[2] in self.admins:
            c.privmsg(nick, "Removing " + cmd[2] + " from admin list ...")
            self.admins.remove(cmd[2])
          else:
            c.privmsg(nick, "No such hostmask on the admin list: '" + cmd[2] + "'")

    # run plugin handlers and return in case one has been found
    try:
      if self.plugin_handle_command(c, cmd, e):
        return
    except PluginError, e:
      c.privmsg(nick, e.msg)
      return

  def on_welcome(self, c, e):
    for channel in self.autojoin_channels:
      c.join(channel)

  # the default method causes the bot to crash on my server
  # Overwriting this is a good idea anyway
  def get_version(self):
    return CTCP_VERSION

def main():
  import argparse
  import sys

  parser = argparse.ArgumentParser(description='A basic flood protection bot.')
  parser.add_argument("--server", '-s', type=str, required=True, help="Address of IRC server")
  parser.add_argument("--port", '-p', type=int, default=6667, help="Port of IRC server")
  parser.add_argument("--nickname", '-n', type=str, default="DontMindMe", help="Bot nickname")
  parser.add_argument("--log-level", type=str, default="INFO", dest='log_level', help="Sets the log level")
  parser.add_argument("--config", "-c", type=str, default="", help="Path to the bot's config file")
  parser.add_argument("--stdout", action="store_true", help="Print log to stdout")
  args = parser.parse_args()

  nick = args.nickname
  server = args.server
  port = args.port
  log_level = args.log_level
  config = args.config
  stdout = args.stdout

  numeric_level = getattr(logging, log_level.upper(), None)
  if not isinstance(numeric_level, int):
    print('Invalid log level: %s' % loglevel)
    sys.exit(-1)

  # logging setup
  logger = logging.getLogger("Core")
  logger.setLevel(numeric_level)

  fmt = logging.Formatter("%(asctime)s %(message)s")

  fh = logging.FileHandler("dontmindme.log")
  fh.setFormatter(logging.Formatter("%(asctime)s [%(name)s::%(levelname)s] %(message)s"))
  fh.setLevel(numeric_level)
  logger.addHandler(fh)

  if stdout:
    sh = logging.StreamHandler()
    sh.setFormatter(logging.Formatter("%(asctime)s [%(name)s::%(levelname)s] %(message)s"))
    sh.setLevel(numeric_level)
    logger.addHandler(sh)

  # no config file supplied, look for one
  if not config:
    if os.path.exists("dontmindme.conf"):
      config = "dontmindme.conf"
    elif os.path.exists("/etc/dontmindme.conf"):
      config = "/etc/dontmindme.conf"
    else:
      logger.error("No config file found, quitting!")
      sys.exit(-1)

  # disable utf-8 decoding of lines, irc is one messy char encoding hell
  irc.client.ServerConnection.buffer_class = irc.client.LineBuffer
  
  logger.info("Starting up DontMindMe.")
  logger.debug("Server: " + server + ":" + str(port) + ", Nickname: " + nick)

  try:
    bot = FloodBot(logger, config, nick, server, port)
    bot.start()
  except BotError, e:
    logger.exception("Bot Error: ")
    logging.shutdown()
  except KeyboardInterrupt:
    logger.info("Application terminated, shutting down ...")
    logging.shutdown()

if __name__ == "__main__":
  main()
