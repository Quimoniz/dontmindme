#!/usr/bin/env python2.7

import time, datetime
import irc.bot
import irc.strings
import irc.client
from irc.dict import IRCDict

MIN_SECONDS_BETWEEN_MESSAGES = 4  # minimal delay in seconds two messages should have
WEBCHAT_MULTIPLIER = 1.5          # additional penalty for webchat users
MAX_FLOOD_SCORE = 15              # maximum score a client can reach before being punished
DEBUG = False

def debug_print(msg):
  global DEBUG
  if DEBUG:
    now = datetime.datetime.now()
    print("[" + now.strftime("%d-%m-%Y %H:%M:%S") + "] " + msg)

class User(object):
  def __init__(self, name, host):
    self.name = name
    self.last_message = None
    self.similar_message_count = 0
    self.flooding = False
    self.last_message_time = 0
    self.flood_score = 0
    self.penalty_count = 0
    
    self.set_host(host)

  def set_host(self, host):
    self.host = host
    
    self.uses_webchat = False
    if self.host.startswith("gateway/web"):
      self.uses_webchat = True

  def update(self, message):
    # a pause of a few seconds between messages keeps flood_score at 0
    msg_length = len(message)
    min_message_delay = MIN_SECONDS_BETWEEN_MESSAGES + (self.uses_webchat*2)
    self.flood_score += (min_message_delay - (time.time() - self.last_message_time))

    # additional penalty for long lines
    self.flood_score += min(11, (msg_length/80)**1.7)
    self.last_message_time = time.time()

    if self.flood_score < 0:
      self.flood_score = 0

    # repeating messages increases flood_score
    # this string comparison could be implemented as a levenshtein ratio
    # to make it more robust against small text changes
    if message == self.last_message:
      self.similar_message_count += 1
      self.flood_score *= (self.similar_message_count)
    else:
      self.similar_message_count = 0
    
    self.last_message = message

    # webchat users are more likely to be evil
    # proven by several studies
    if self.uses_webchat:
      self.flood_score *= WEBCHAT_MULTIPLIER

    # TODO check for nazi scum catchphrases
    # TODO Decrease flood score for registered users

    # flood_score threshhold
    if self.flood_score >= MAX_FLOOD_SCORE:
      self.set_flooding(True)
      self.penalty_count += 1
      
      # reset flood_score once a user is blamed
      # to avoid keeping a user in jail repeatedly
      self.flood_score = 0
    else:
      self.set_flooding(False)

  def set_flooding(self, flag):
    self.flooding = flag

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

class FloodBot(irc.bot.SingleServerIRCBot):
  def __init__(self, nickname, server, port, channel):
    irc.bot.SingleServerIRCBot.__init__(self, [(server, port)], nickname, nickname)
    self.channel = channel
    self.blacklist = set()
    self.whitelist = set()

  # checks if a user is a channel op in one of our channels
  def is_user_admin(self, nick):
    for _, channel in self.channels.items():
      if channel.is_oper(nick):
        return True

    return False

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

  def on_join(self, c, e):
    channel = e.target
    nick = e.source.nick
 
    # Don't try to voice ourself
    if nick == c.get_nickname():
      return

    if e.source.host not in self.blacklist:
      # auto voice newcomers
      c.mode(channel, "+v " + nick)
      debug_print("'" + e.source.nick + "' gets voiced!")
    else:
      debug_print("'" + e.source.nick + "' is already blacklisted, no voice for you!")

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
      debug_print("Unknown user: '" + nick + "'. I'm scared!")
      return

    message = e.arguments[0].split(":", 1)

    if user.host == "":
      user.set_host(e.source.host)

    # don't punish whitelisted users
    if nick.lower() in self.whitelist:
      return
    
    user.update(message)

    # user has been found flooding
    if user.flooding:
      debug_print("User '" + user.name + "' is flooding!")
      c.mode(channel_name, "-v " + nick)
      self.blacklist.add(e.source.host)
      
      user.set_flooding(False)

  def on_privmsg(self, c, e):
    nick = e.source.nick
    
    if not self.is_user_admin(nick):
      debug_print("Unauthorized command by user '" + nick + "'")
      return False
    
    # extract message from arguments, strip and lower
    msg = e.arguments[0].split(":", 1)[0].strip().lower()
   
    # commands have to start with '!'
    if not msg.startswith("!"):
      return False
  
    debug_print("User '" + nick + "' issued command: '" + msg + "'")

    # command parsing
    cmd = msg.split(" ")

    # whitelist management
    if cmd[0] == "!whitelist":
      if len(cmd) < 2:
        c.privmsg(nick, "!whitelist add <nick>|del <nick>|list - Manage the bot's whitelist")
        return
      
      if cmd[1] == "list":
        if len(self.whitelist):
          c.privmsg(nick, "Whitelist: " + ','.join(self.whitelist))
        else:
          c.privmsg(nick, "Whitelist is empty")
        return

      if len(cmd) < 3:
        return
      
      target = cmd[2]
      
      if cmd[1] == "add":
        self.whitelist.add(target)
        c.privmsg(nick, "User '" + target + "' added to whitelist")
      elif cmd[1] == "del":
        if target in self.whitelist:
          self.whitelist.remove(target)
          c.privmsg(nick, "User '" + target + "' removed from whitelist")
        else:
          c.privmsg(nick, "User '" + target + "' not on whitelist")
    
    # blacklist management
    elif cmd[0] == "!blacklist":
      if len(cmd) < 2:
        c.privmsg(nick, "!blacklist clear - Reset the bot's blacklist")
        return

      if cmd[1] == "clear":
        self.blacklist.clear()
        c.privmsg(nick, "Blacklist cleared")

    # let the bot join a channel
    elif cmd[0] == "!join":
      if len(cmd) < 2:
        c.privmsg(nick, "!join <#channel> - Tell the bot to join a certain channel")
        return
      
      c.join(cmd[1])

    # let the bot leave a channel
    elif cmd[0] == "!part":
      if len(cmd) < 2:
        c.privmsg(nick, "!part <#channel> - Tell the bot to part a certain channel")
        return
      
      c.part(cmd[1])
 
  def on_welcome(self, c, e):
    c.join(self.channel)

  # the default method causes the bot to crash on my server
  # Overwriting this is a good idea anyway
  def get_version(self):
    return "DontMindMe - Flood Protection Bot 0.1"

def main():
  global DEBUG
  import argparse

  parser = argparse.ArgumentParser(description='A basic flood protection bot.')
  parser.add_argument("--server", '-s', type=str, required=True, help="Address of IRC server")
  parser.add_argument("--port", '-p', type=int, default=6667, help="Port of IRC server")
  parser.add_argument("--channel", '-c', type=str, required=True, help="Channel to join after connecting")
  parser.add_argument("--nickname", '-n', type=str, default="DontMindMe", help="Bot nickname")
  parser.add_argument("--debug", '-d', action='store_true', help="Print debug messages")
  args = parser.parse_args()

  nick = args.nickname
  server = args.server
  port = args.port
  channel = args.channel
  DEBUG = args.debug

  # disable utf-8 decoding of lines, irc is one messy char encoding place
  irc.client.ServerConnection.buffer_class = irc.client.LineBuffer
 
  print("Starting up flood protection ...")
  debug_print("Server: " + server + ":" + str(port) + ", Channel: " + channel + ", Nickname: " + nick)
  bot = FloodBot(nick, server, port, channel)
  bot.start()

if __name__ == "__main__":
  main()
