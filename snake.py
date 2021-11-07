#!/usr/bin/python

import sys
import curses
import random
from collections import deque

def parseconfig(args):
    configconfig = {
        'help' : {
            None: """ 
snake.py

An implementation of Snake, in python, for vt100-like terminals
    by Benjamin Newman

Run "snake.py help <topic>" for more information
    (help topics: rules, keys, options)
""",
            'options': """ 
snake.py [[<opt_group>] <opt_name> <opt_value>] etc.
options:
    help
        display help text, 'help <topic>' for more details
        (help topics: rules, keys, options)
    player
        count (1,2) -- the number of players
        color (cyan,magenta) -- the color of player one
    world
        wrap (0,1,2) - wrap the world around on this many axes
        delay (int) - wait this many milliseconds between frames
    grow
        start (int) - snakes begin with this many tail segments
        time (float) - snakes grow all the time at this rate
        food (int) - snakes grow this many segments when they eat food
    score
        time (int) - player scores increase constantly at this rate
        food (int) - players score this many points when they eat food
        end (int) - the survivor of a round gets this many additional points
    until
        points (int) - the game ends when a player has this many points
        rounds (int) - the game ends after this many rounds
""",
            'keys': """ 
snake.py controls:

Use the WASD or arrow keys to control your snake.

In a one-player game either set of keys can be used.
In a two-player game, player one uses WASD and player two uses the arrows.

At round start the game waits for the player(s) to choose a direction.

The tab and enter keys can be used to pause the game.
When paused, press G (for "go") to resume or H (for "halt") to exit.
""",
            'rules': """ 
Snake rules:

Move your snake around the board to collect food and avoid crashing.
Snakes move constantly and can only change direction, not speed.
Running into a wall or any snake's tail is fatal and ends the round.

Snakes grow and score points by eating food (by default).

Number of players, growth rate, the effect of eating food,
  whether the grid wraps around, and other parameters
  can be adjusted by passing options on the command line.
    (See "help options" for more information.)

A one-player game lasts one round.
A two-player game lasts a number of rounds (default: 5).

Only the player who survives a round gets to add their score for
  that round to their total score for the game.
"""
        },
        'player': {
            'count': (int, (1,2), 1),
            'color': (str, ('cyan','magenta'), 'cyan'),
        },
        'world': {
            'wrap': (int, (0,1,2), 0),
            'delay': (int, None, 100),
        },
        'grow': {
            'start': (int, None, 0),
            'time': (float, None, 0),
            'food': (int, None, 1),
        },
        'score': {
            'time': (int, None, 0),
            'food': (int, None, 1),
            'end': (int, None, 0),
            # TO-DO -- make forfeit optional
        },
        'until': {
            'points': (int, None, None),
            'rounds': (int, None, 5),
        },
    }

    config = {}
    convert, choices, default = 0, 1, 2

    for l1key in configconfig:
        config[l1key] = {}
        for l2key in configconfig[l1key]:
            config[l1key][l2key] = configconfig[l1key][l2key][default]

    l1key = None
    l2key = None

    try:
        for word in args:
            if l1key is not None and isinstance(l2key, str):
                configitem = configconfig[l1key][l2key]
                if isinstance(configitem, str):
                    raise ValueError('Can\'t accept other options after "%s %s"' % (l1key, l2key))
                value = configitem[convert](word)
                if configitem[choices] is None or value in configitem[choices]:
                    config[l1key][l2key] = value
                    l2key = None
                else:
                    raise ValueError('Bad value "%s" for option "%s %s"' % (word, l1key, l2key))
            elif word in configconfig:
                l1key = word
                l2key = False
            elif l1key is not None and word in configconfig[l1key]:
                l2key = word
            else:
                raise ValueError('Unknown option "%s"' % word)

        if l1key == "help":
            print(configconfig[l1key][l2key or None])
            sys.exit()
        elif l2key is False:
            raise ValueError('No sub-option passed for option group "%s"' % l1key)
        elif l2key is not None:
            raise ValueError('No value passed for option "%s %s"' % (l1key, l2key))
    except ValueError as e:
        print(configconfig['help']['options'])
        print(e)
        sys.exit()

    return config

colors = {} # can't define the actual colors until we start curses
oppositecolor = { 'magenta': 'cyan', 'cyan': 'magenta' }

startpos = {
    1: { 0: ((10,11),), 1: ((10,11),), 2: ((10,11),) },

    2: {
        0: ((10,0), (11,22)),
        1: ((10,5), (11,17)),
        2: ((5,5), (16,17)),
    }
}

directions = { 'up': (-1,0), 'down': (1,0), 'left': (0,-1), 'right': (0,1) }

oppositedirections = {
    None: None,
    'up': 'down',
    'down': 'up',
    'left': 'right',
    'right': 'left',
}

keys = {
    ord('w'): ('wasd', 'up'),
    ord('a'): ('wasd', 'left'),
    ord('s'): ('wasd', 'down'),
    ord('d'): ('wasd', 'right'),

    # ord('i'): ('ijkl', 'up'),
    # ord('j'): ('ijkl', 'left'),
    # ord('k'): ('ijkl', 'down'),
    # ord('l'): ('ijkl', 'right'),

    curses.KEY_UP: ('arrows', 'up'),
    curses.KEY_LEFT: ('arrows', 'left'),
    curses.KEY_DOWN: ('arrows', 'down'),
    curses.KEY_RIGHT: ('arrows', 'right'),

    ord('\t') : (None, 'pause'),
    ord('\n') : (None, 'pause'),
}

class player(object):
    def __init__(self, game, side, color):
        self.game = game
        self.side = side
        self.color = color
        self.gamescore = 0

    def reset(self, position):
        self.roundscore = 0
        self.dead = False

        self.direction = None
        self.olddirection = None

        self.newhead = None
        self.oldhead = None

        self.tail = deque()
        self.tail.append(position)
        self.game.empty.remove(position)

        self.length = self.game.config['grow']['start']

class game(object):

    def __init__(self, config):
        self.config = config

        self.boardbounds = ((0,15), (23,63))
        if self.config['world']['wrap'] > 0:
            self.boardbounds = ((0,16), (23,62))

        self.boardsize = (self.boardbounds[1][0] - self.boardbounds[0][0] - 1,
                          (self.boardbounds[1][1] - self.boardbounds[0][1]) // 2 - 1)

        self.offset = (self.boardbounds[0][0] + 1, self.boardbounds[0][1] + 1)

    def getkeys(self, w):
        keylist = []
        while True:
            key = w.getch()
            if key == -1: break
            else: keylist.append(key)
        return keylist

    def handlekeys(self, w, canpause=True):
        for key in self.getkeys(w):
            if key in keys:
                padname, action = keys[key]

                if action == 'pause' and canpause:
                    self.pause(w)

                elif padname is not None:
                    if action != oppositedirections[self.playerkeys[padname].olddirection]:
                        self.playerkeys[padname].direction = action

    def pause(self, w, message=" =PAUSE="):
        for p in self.players:
            self.sidepanelmessage(w, 18, p.side, [message, None, " G to Go", "H to Halt"])
        self.refresh(w)

        paused = True
        while paused:
            curses.napms(100)

            for key in self.getkeys(w):
                if key == ord('g'): paused = False
                elif key == ord('h'): sys.exit()

        self.drawscoredisplays(w)
        self.refresh(w)
        curses.napms(self.config['world']['delay'])

    def refresh(self, w):
        w.move(23,79)
        w.refresh()

    def sidepanelmessage(self, w, line, side, message=[], color='white'):
        column = 2 + (self.boardbounds[1][1] + 2) * side
        for part in message:
            if part is not None:
                w.addstr(line, column, part, colors[color])
            line += 1

    def drawscoredisplays(self, w):
        for p in self.players:
            self.sidepanelmessage(w, 0, p.side, [' ' * 10] * (self.boardbounds[1][0] + 1))

            num = ('ONE', 'TWO')[p.side]
            message = ["PLAYER " + num, None, "SCORE: " + str(p.roundscore), None]
            if len(self.players) > 1: message.append("TOTAL: " + str(p.gamescore))
            self.sidepanelmessage(w, 2, p.side, message, p.color)

    def setfood(self, w):
        if self.food is None:
            if (self.config['grow']['food'] != 0 or
                self.config['score']['food'] != 0):
                self.food = random.choice(list(self.empty))

                w.addch(self.food[0]+self.offset[0], self.food[1]*2+self.offset[1]+1,
                        curses.ACS_DIAMOND, colors['white'])

    def drawboard(self, w):
        for i in range(self.boardbounds[0][0], self.boardbounds[1][0]):
            for q in (0,1): w.addch(i, self.boardbounds[q][1], curses.ACS_VLINE)
        for i in range(self.boardbounds[0][1], self.boardbounds[1][1]):
            for q in (0,1): w.addch(self.boardbounds[q][0], i, curses.ACS_HLINE)

        w.addch(self.boardbounds[0][0], self.boardbounds[0][1], curses.ACS_ULCORNER)
        w.addch(self.boardbounds[0][0], self.boardbounds[1][1], curses.ACS_URCORNER)
        w.addch(self.boardbounds[1][0], self.boardbounds[0][1], curses.ACS_LLCORNER)
        w.addch(self.boardbounds[1][0], self.boardbounds[1][1], curses.ACS_LRCORNER)

        if self.config['world']['wrap'] >= 1:
            for i in range(self.boardbounds[0][0]+1, self.boardbounds[1][0]):
                w.addch(i, self.boardbounds[0][1], curses.ACS_RTEE)
                w.addch(i, self.boardbounds[0][1]-1, curses.ACS_HLINE)
                w.addch(i, self.boardbounds[1][1], curses.ACS_LTEE)
                w.addch(i, self.boardbounds[1][1]+1, curses.ACS_HLINE)

            if self.config['world']['wrap'] == 2:
                for i in range(self.boardbounds[0][1]+2, self.boardbounds[1][1], 2):
                    w.addch(self.boardbounds[0][0], i, curses.ACS_BTEE)
                    w.addch(self.boardbounds[1][0], i, curses.ACS_TTEE)

        self.drawscoredisplays(w)

    def drawhead(self, p, w, char='@'):
        w.addstr(p.tail[-1][0]+self.offset[0], p.tail[-1][1]*2+self.offset[1], '(')
        w.addstr(p.tail[-1][0]+self.offset[0], p.tail[-1][1]*2+self.offset[1]+2, ')')

        w.addstr(p.tail[-1][0]+self.offset[0],
                 p.tail[-1][1]*2+self.offset[1]+1,
                 char, colors[p.color])

    def playround(self, w):
        self.empty = set()
        for i in range(self.boardsize[0]):
            for j in range(self.boardsize[1]):
                self.empty.add((i,j))

        for p in range(self.config['player']['count']):
            self.players[p].reset(
                startpos[self.config['player']['count']][self.config['world']['wrap']][p])

        w.clear()
        self.drawboard(w)

        self.food = None
        self.setfood(w)

        # wait for players to be ready
        for p in self.players: self.drawhead(p, w, '?')
        self.refresh(w)
        while [p for p in self.players if p.direction is None]:
            curses.napms(100)
            self.handlekeys(w, False)
            for p in self.players:
                if p.direction is not None:
                    self.drawhead(p, w, '!')
            self.refresh(w)

        # count down to start
        for i in (3,2,1):
            for p in self.players: self.drawhead(p, w, str(i))
            self.refresh(w)
            curses.beep()
            curses.napms(500)

        for p in self.players: self.drawhead(p, w)
        self.refresh(w)
        curses.napms(self.config['world']['delay'])

        # play the round
        while not [p for p in self.players if p.dead]:
            self.playframe(w)

        for p in self.players:
            if not p.dead:
                p.roundscore += self.config['score']['end']
                if p.roundscore >= 0: p.gamescore += p.roundscore

        for i in range(3):
            curses.beep()
            curses.napms(200)

        # round over display
        self.drawscoredisplays(w)

        if len(self.players) > 1:
            roundwinner = "  NOBODY"
            color = 'white'

            for p in self.players:
                if not p.dead:
                    roundwinner = "PLAYER " + ('ONE', 'TWO')[p.side]
                    color = p.color

            for p in self.players:
                self.sidepanelmessage(w, 11, p.side, [roundwinner, "WINS ROUND"], color)

            self.pause(w, "ROUND END")

        self.roundsplayed += 1

    def playgame(self, w):
        self.players = [player(self, 0, self.config['player']['color'])]
        if self.config['player']['count'] == 2:
            self.players.append(player(self, 1, oppositecolor[self.config['player']['color']]))

        self.playerkeys = {
            'wasd': self.players[0],
            # 'ijkl': self.players[-1],
            'arrows': self.players[-1],
        }

        self.roundsplayed = 0

        curses.cbreak()
        w.timeout(0)

        curses.init_pair(1, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_CYAN, curses.COLOR_BLACK)

        colors['white'] = curses.A_BOLD
        colors['magenta'] = curses.color_pair(1) | curses.A_BOLD
        colors['cyan'] = curses.color_pair(2) | curses.A_BOLD

        while True:
            self.playround(w)
            if (len(self.players) == 1 or
                self.roundsplayed >= self.config['until']['rounds'] or
                (self.config['until']['points'] is not None and
                 [p for p in self.players if p.gamescore >= self.config['until']['points']])):
                break

        self.drawscoredisplays(w)

        if len(self.players) > 1:
            # display game winner message
            color = 'white'
            message = ["GAME TIED"]

            for p in self.players:
                if p.gamescore > min([p.gamescore for p in self.players]):
                    message = ["PLAYER " + ('ONE', 'TWO')[p.side], "WINS GAME"]
                    color = p.color

            for p in self.players:
                self.sidepanelmessage(w, 11, p.side, message, color)

        self.pause(w, "GAME OVER")

    def start(self, w):
        # TO-DO display instructions?
        while True:
            self.playgame(w)

    def moveby(self, p, d):
        dy, dx = directions[d]
        y = p[0]+dy
        x = p[1]+dx
        if self.config['world']['wrap'] >= 1:
            x %= self.boardsize[1]
            if self.config['world']['wrap'] == 2:
                y %= self.boardsize[0]
        return (y,x)

    def playframe(self, w):

        for p in self.players: p.olddirection = p.direction

        self.handlekeys(w)

        for p in self.players:
            p.oldhead = p.tail[-1]
            p.newhead = self.moveby(p.oldhead, p.direction)
            p.length += self.config['grow']['time']
            if p.newhead == self.food:
                self.food = None
                p.roundscore += self.config['score']['food']
                if p.roundscore < 0: p.roundscore = 0
                p.length += self.config['grow']['food']
                if p.length < 0: p.length = 0
                curses.beep()

        erasesegments = []

        # mark excess tail segments for removal
        for p in self.players:
            while len(p.tail) > p.length:
                lastsegment = p.tail.popleft()
                self.empty.add(lastsegment)
                erasesegments.append(lastsegment)

        # check if a player died
        for p in self.players:
            if p.newhead not in self.empty:
                p.dead = True

        # draw new leading tail segment
        space = ord(' ')
        hline = curses.ACS_HLINE
        lines = {
            # going straight
            ('up', 'up'): [space, curses.ACS_VLINE, space],
            ('down', 'down'): [space, curses.ACS_VLINE, space],
            ('left', 'left'): [hline, hline, hline],
            ('right', 'right'): [hline, hline, hline],
            # turning left
            ('up', 'right'): [hline, curses.ACS_LRCORNER, space],
            ('down', 'left'): [space, curses.ACS_ULCORNER, hline],
            ('left', 'up'): [hline, curses.ACS_URCORNER, space],
            ('right', 'down'): [space, curses.ACS_LLCORNER, hline],
            # turning right
            ('up', 'left'): [space, curses.ACS_LLCORNER, hline],
            ('down', 'right'): [hline, curses.ACS_URCORNER, space],
            ('left', 'down'): [hline, curses.ACS_LRCORNER, space],
            ('right', 'up'): [space, curses.ACS_ULCORNER, hline]
        }

        for p in self.players:
            if p.tail:
                line = lines[(p.direction, p.olddirection)]
                for i in range(3):
                    w.addch(p.tail[-1][0]+self.offset[0], p.tail[-1][1]*2+i+self.offset[1],
                            line[i], colors[p.color])

        # erase tail segments marked for removal
        for s in erasesegments:
            w.addstr(s[0]+self.offset[0] ,2*s[1]+self.offset[1], "   ")

        # detect a direct crash
        if (len(self.players) == 2 and
            self.players[0].oldhead == self.players[1].newhead and
            self.players[1].oldhead == self.players[0].newhead):
            for p in self.players:
                p.newhead = p.oldhead
                p.dead = True

        # draw new head
        for p in self.players:
            p.tail.append(p.newhead)
            if p.dead:
                self.drawhead(p, w, 'X')
            else:
                self.drawhead(p, w)
                self.empty.remove(p.newhead)

        # draw | between player heads if they're adjacent
        if (len(self.players) == 2 and
            self.players[0].tail[-1][0] == self.players[1].tail[-1][0] and
            self.players[0].tail[-1][1] - self.players[1].tail[-1][1] in (-1, 1)):
            w.addstr(self.players[0].tail[-1][0]+self.offset[0],
                     self.players[0].tail[-1][1]+self.players[1].tail[-1][1]+self.offset[1]+1,
                     '|')

        self.setfood(w)

        self.drawscoredisplays(w)
        self.refresh(w)

        curses.napms(self.config['world']['delay'])


curses.wrapper(game(parseconfig(sys.argv[1:])).start)
