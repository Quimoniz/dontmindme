DontMindMe
==========
A general, all-purpose IRC bot. Core functionality includes connecting to a server and staying online and can be extended by loading plugins at runtime. Only admins are allowed to run commands. Either you authenticate yourself using a shared secret or you have channel operator status in one of the channels the bot is in. This behaviour will be changed in the future.

Commands
--------
The core command set includes:

* !plugin - Loading/unloading of plugins
    * list - List available plugins (running plugins are marked with an asterisk)
    * load <name>- Load a plugin
    * unload <name> - Unload a plugin
    * reload <name> - Reload a plugin
* !admin - Manage administrators. This only works on administrators that authenticated using !secret.
    * list - List authenticated hostmask
    * remove <hostmask> - Remove admin status from a hostmask
    * purge - Remove all hostmasks (including your own, if you are on this list)
* !secret - Authenticates a user that knows the shared secret with the bot.

Plugins
-------
Plugins are single python scripts following this basic format:

    import logging
    
    logger = logging.getLogger("Core.MyPlugin")

    class MyPlugin:
      _name_ = "MyPlugin"
      _author_ = "My Name"
      _description_ = "This does absolutely nothing!"

      def __init__(self, plugin):
        self.plugin = plugin

Using the plugin object, you can register command and/or event handlers. Command handlers will only work in a private query with the bot and only with commands that start with an exclamation mark (for now). Capturing events allows you to do more complex jobs (see the antispam plugin, for example).

A more "useful" example:

    import logging
    
    logger = logging.getLogger("Core.MyPlugin")

    class MyPlugin:
      _name_ = "MyPlugin"
      _author_ = "My Name"
      _description_ = "This does absolutely nothing!"

      def __init__(self, plugin):
        self.plugin = plugin
        self.plugin.add_event_handler("PUBMSG", self.pubmsg_handler)
        self.plugin.add_command_handler("!test", self.test_handler)

      def pubmsg_handler(self, conn, data):
        # echos back to the channel everything someone says
        conn.privmsg(data.target, data.arguments[0].split(":", 1)

      def test_handler(self, conn, params, data):
        conn.privmsg(data.source.nick, "Hello %s! This is a command handler." % (data.source.nick))

Possible events are:

* PRIVMSG (Private message)
* PUBMSG (Public message, in a channel)
* JOIN (User joins a channel. This can also be the bot itself!)
* PART (User leaves a channel. This can also be the bot itself!)
* PRIVNOTICE (Private notice)

Existing plugins
----------------
* antispam - Watches all channels the bot is in for spam and sets mode +q on spamming users through ChanServ (might only work on Freenode)
* botcontrol - Offers some basic control commands like !join, !part, !nick
* nickserv - Tries to identify with NickServ. The password has to be stored in the config file.

Config
------
The config file is a simple, ini-format based text file. See dontmindme.conf.example for more information


