#Constants
import random
import cardtype
import visibilities
import owners
import controlers
import effects
import deck_builder
import globe
import ai_hint
import error_checker
import json

class MyEncoder(json.JSONEncoder):
        def default(self, o):
            return o.__dict__    


class pile:
	#List of cards
	contents = None
	visibility = visibilities.PUBLIC
	owner = None
	name = ""

	#I'll start the deck empty
	def __init__(self,name,owner = None,visibility = visibilities.PUBLIC):
		self.name = name
		self.owner = owner
		self.visibility = visibility
		self.contents = []

	def shuffle(self):
		random.shuffle(self.contents)

	def size(self):
		return len(self.contents) 

	def can_draw(self):
		if self.size() > 0:
			return True
		else:
			return False

	def draw(self):
		if len(self.contents) > 0:
			return self.contents.pop()
		else:
			return None

	def add(self,card):
		self.contents.append(card)

	def add_bottom(self,card):
		self.contents.insert(0,card)

	def get_count(self,find_type = cardtype.ANY):
		if find_type == cardtype.ANY:
			return self.size()
		else:
			#if self.visibility == visibilities.PUBLIC \
			#	or (self.visibility == visibilities.PRIVATE and self.owner.pid = pid)
			count = 0
			for c in self.contents:
				if c.ctype_eq(find_type):
					count += 1
			return count

class playing(pile):
	power = 0
	card_mods = []
	double_modifier = 0
	played_this_turn = []

	special_options = []

	def no_mod(self,card,player):
		return card.play_action(player)

	def __init__(self,name,owner = None,visibility = visibilities.PUBLIC):
		self.name = name
		self.owner = owner
		self.visibility = visibility
		self.contents = []
		self.played_this_turn = []
		self.special_options = []
		self.card_mods = [self.no_mod]


	def turn_end(self):
		self.power = 0
		self.played_this_turn = []
		self.special_options = []
		self.card_mods = [self.no_mod]

		#self.owner.persona.set_modifiers()
		self.double_modifier = 0
		while self.size() > 0:
			c = self.contents.pop()
			if c.owner_type == owners.PLAYER:
				c.owner.discard.add(c)
			elif c.owner_type == owners.MAINDECK:
				globe.boss.main_deck.add(c)
			elif c.owner_type == owners.LINEUP:
				globe.boss.lineup.add(c)
			elif c.owner_type == owners.VILLAINDECK:
				globe.boss.supervillain_stack.add(c)

	def add(self,card):
		self.play(card)


	def play(self,card,ongoing = False):
		if globe.DEBUG:
			if card.owner != self.owner:
				if card.owner_type == owners.PLAYER:
					print(f"{self.owner.persona.name} playing {card.owner.persona.name}'s {card.name}",flush = True)
				else:
					print(f"{self.owner.persona.name} playing {card.owner.name}'s {card.name}",flush = True)
			else:
				print(f"{card.name} being played",flush = True)
		if not ongoing:
			card.times_played += 1
			self.contents.append(card)
		modifier = 0

		if not ongoing:
			self.played_this_turn.append(card)

		# SO that the mods can delete themselves afterwards
		assemble = []
		for mod in self.card_mods:
			assemble.append(mod)

		for mod in assemble:
			modifier += mod(card,self.owner)
		#modifier = card.play_action(self.owner)
		#modifier = post_power()

		for i in range(self.double_modifier):
			modifier *= 2

		#print("MOD WAS",modifier)
		self.power += modifier
		
		#print("PLAYED!", self.power, self)

	def parallax_double(self):
		self.power *= 2
		self.double_modifier += 1

	def plus_power(self,power):
		for i in range(self.double_modifier):
			power *= 2
		self.power += power


class ongoing_pile(pile):

	def begin_turn(self):
		for c in self.contents:
			self.owner.played.play(c,True)

class supervillain_pile(pile):
	current_sv = None

class player:
	pid = -1
	score = 0
	vp = 0
	deck = None
	hand = None
	discard = None
	ongoing = None
	played = None
	controler = None
	persona = None
	under_superhero = None
	over_superhero = None

	gain_redirect = []
	gained_this_turn = []
	discarded_this_turn = []
	discount_on_sv = 0

	#For cards to use on generic rare things
	#like if they have to detect discarding cards and such
	#I should switch the personas that detect drawing to use this as well
	#and passing
	#and discarding
	#and gaining vps
	triggers = []
	
	sv_bought_this_turn = False
	# For cards like the riddler

	played_riddler = False

	def __init__(self,pid, controler):
		self.controler = controler
		self.pid = pid

		self.deck = pile("Deck",self, visibilities.SECRET)
		self.hand = pile("Hand",self, visibilities.PRIVATE)
		self.discard = pile("Discard",self)
		self.under_superhero = pile("Under Persona",self)
		self.over_superhero = pile("Over Persona",self)
		self.ongoing = ongoing_pile("Ongoing",self)
		self.played = playing("Played",self)

		#self.vp = 5

		#These should be reinitialized or they share values with all insatnces
		self.gain_redirect = []
		self.gained_this_turn = []
		self.discarded_this_turn = []
		self.triggers = []

		self.deck.contents = deck_builder.get_starting_deck(self)
		self.discard.contents = deck_builder.debug_discard(self)

		for i in range(5):
			self.hand.add(self.deck.draw())

	def choose_persona(self,persona_list):
		self.persona = self.controler.choose_persona(persona_list)
		persona_list.remove(self.persona)
		self.persona.set_owner(self)

		#self.persona = self.persona(self)
		self.persona.reset()

	def turn(self):
		#unfreeze all cards in lineup
		for c in globe.boss.lineup.contents:
			if self.pid in c.frozen:
				c.frozen.remove(self.pid)

		discarded_this_turn = []

		self.persona.ready()
		self.ongoing.begin_turn()
		self.controler.turn()
		#self.end_turn()

	#Draws 'num' cards.  Returns the last card that was drawn
	def draw_card(self,num = 1,from_card = True):
		print("PLAYER HAS BEEN TOLD TO DRAW",self.persona.name,flush = True)
		all_drawn = []
		
		if from_card:
			self.persona.draw_power()
		for i in range(num):
			#Check that there is a card to draw
			if not self.manage_reveal():
				#This will break things, but is so rare it shoudlnt happen really
				print("ERR: No more cards in deck",flush = True)
				return None
			drawn_card = self.deck.draw()
			all_drawn.append(drawn_card)
			self.hand.add(drawn_card)
		
		for t in self.triggers:
			t("draw",[num,from_card,all_drawn],self)
		
		return drawn_card

	def reveal_card(self,public = True):
		if not self.manage_reveal():
			return None
		top_card = self.deck.contents[-1]
		if public:
			reveal_text = f"{top_card.name} was on the top of {self.persona.name}'s deck."
			effects.reveal(reveal_text,self,[top_card])
		return top_card

	def manage_reveal(self):
		if not self.deck.can_draw():
			self.deck.contents = self.discard.contents
			self.discard.contents = []
			self.deck.shuffle()
			if self.deck.size() == 0:
				return False
			return True
		else:
			return True

	def play(self, cardnum):
		self.played.play(self.hand.contents.pop(cardnum))


	def play_c(self, card):
		if card in self.hand.contents:
			self.hand.contents.remove(card)
			self.played.play(card)


	def play_and_return(self, card, pile):
		self.played.play(card)
		card.pop_self()
		#self.played.contents.remove(card)
		pile.add(card)

	def buy_supervillain(self):
		print("Trying to buy sv",globe.boss.supervillain_stack.contents[-1].cost - self.discount_on_sv,flush = True)
		if globe.boss.supervillain_stack.current_sv == globe.boss.supervillain_stack.contents[-1] \
				and self.played.power >= globe.boss.supervillain_stack.contents[-1].cost - self.discount_on_sv:
			if globe.DEBUG:
				print(f" {globe.boss.supervillain_stack.contents[-1].name} bought")
			#self.sv_bought_this_turn = True
			#self.played.power -= globe.boss.supervillain_stack.contents[-1].cost - self.discount_on_sv
			return self.gain(globe.boss.supervillain_stack.contents[-1],bought = True,defeat = True)
			#return True
		return False

	def buy_kick(self):
		if globe.boss.kick_stack.size() > 0 and self.played.power >= globe.boss.kick_stack.contents[-1].cost:
			if globe.DEBUG:
				print(f"kick bought")
			#globe.boss.kick_stack.contents[-1].bought = True
			#self.played.power -= globe.boss.kick_stack.contents[-1].cost
			return self.gain(globe.boss.kick_stack.contents[-1],bought = True)
			#return True
		return False

	"""def riddle(self):
		if self.played_riddler and globe.boss.main_deck.size() > 0 and self.played.power >= 3:
			self.played.power -= 3
			self.gain(globe.boss.main_deck.contents)
			return True
		return False"""

	def gain_a_weakness(self):
		if globe.boss.weakness_stack.size() > 0:
			return self.gain(globe.boss.weakness_stack.contents[-1])
			#return True
		return False

	def discard_a_card(self,card):
		self.persona.discard_power()
		for t in self.triggers:
			t("discard",[card],self)
		self.discard.add(card.pop_self())
		self.discarded_this_turn.append(card)

	def card_has_been_passed(self,card):
		self.persona.card_pass_power()
		for t in self.triggers:
			t("pass",[card],self)

#depreciated
	def buy(self,cardnum):
		if cardnum < 0 or cardnum >= len(globe.boss.lineup.contents):
			return False
		card = globe.boss.lineup.contents[cardnum]
		if self.played.power >= card.cost:
			#card.bought = True
			if globe.DEBUG:
				print(f"{card.name} bought")
			#self.played.power -= card.cost
			return self.gain(globe.boss.lineup.contents[cardnum],bought = True)
			#return True
		return False

	def buy_c(self,card):
		if self.played.power >= card.cost and len(card.frozen) == 0:
			#card.bought = True
			if globe.DEBUG:
				print(f"{card.name} bought")
			#self.played.power -= card.cost
			return self.gain(card,bought = True)
			#return True
		return False

	def gain(self, card,bought = False,defeat = False):

		#Trying to buy card. Have not payed yet, but funds have been secured
		if bought:
			#card is frozen, cannot buy
			if len(card.frozen) != 0:
				return False

			#Trying to buy card.  Card may resist, if not, it may do other effects
			if not card.buy_action(self,bought):
				print("Rejected",flush = True)
				return False
			# All checks passed, paying
			if defeat:
				#avoids negative
				self.played.power -= max(card.cost - self.discount_on_sv,0)
			else:
				self.played.power -= card.cost

		card.pop_self()
		self.gained_this_turn.append(card)

		redirected = False
		if len(self.gain_redirect) > 0:
			assemble = []
			for re in self.gain_redirect:
				assemble.append(re)


			for re in assemble:
				redirect_responce = re(self,card)
				if not redirected and redirect_responce[0]:
					if len(redirect_responce) == 3:
						redirect_responce[1].contents.insert(0,card)
					else:
						redirect_responce[1].add(card)
					redirected = True

		card.set_owner(player=self)

		if not redirected:
			self.discard.add(card)

		return True

	def gain_vp(self,amount):
		self.vp += amount
		self.persona.gain_vp_power()
		for t in self.triggers:
			t("gain_vp",[amount,self])
			

	def discard_hand(self):
		for c in self.hand.contents.copy():
			self.discard_a_card(c)
		#self.discard.contents.extend(self.hand.contents)
		#self.hand.contents = []


	def end_turn(self):
		for t in self.triggers:
			t("end_turn",[],self)
		self.triggers = []
		self.gain_redirect = []
		self.discount_on_sv = 0
		for c in self.played.played_this_turn:
			c.end_of_turn()
		self.discard_hand()
		for c in self.played.played_this_turn:
			c.next_turn()
		self.played.turn_end()
		self.persona.reset()
		self.gained_this_turn = []
		self.discarded_this_turn = []
		#for i in range(5):
		self.draw_card(num=5, from_card = False)
		self.sv_bought_this_turn = False
		self.calculate_vp()


	def calculate_vp(self):
		assemble = []
		#if None in self.discard.contents:
		assemble.extend(self.deck.contents)
		assemble.extend(self.discard.contents)
		assemble.extend(self.hand.contents)
		assemble.extend(self.played.contents)
		assemble.extend(self.ongoing.contents)
		vp = 0
		for c in assemble:
			vp += c.calculate_vp(assemble)
		self.score = vp + self.vp
		return self.score





class model:
	main_deck = None
	weakness_stack = None
	kick_stack = None
	supervillain_stack = None
	lineup = None
	players = []
	player_score = []
	destroyed_stack = None
	notify = None
	whose_turn = 0
	persona_list = []
	turn_number = 0

	dupe_checker = None

	#initialize Game
	def __init__(self,number_of_players=2):
		self.main_deck = pile("Main Deck")
		self.main_deck.contents = deck_builder.initialize_deck()
		self.weakness_stack = pile("Weakness Stack")
		self.weakness_stack.contents = deck_builder.initialize_weaknesses()
		self.kick_stack = pile("Kick Stack")
		self.kick_stack.contents = deck_builder.initialize_kicks()
		self.supervillain_stack = supervillain_pile("SV Stack")
		self.supervillain_stack.contents = deck_builder.initialize_supervillains()
		self.supervillain_stack.current_sv = self.supervillain_stack.contents[-1]
		self.lineup = pile("Linup")
		self.destroyed_stack = pile("Destroyed")
		self.persona_list = deck_builder.get_personas()

		for c in range(5):
			self.lineup.add(self.main_deck.draw())

		#2 human players for initialization
		
		invisible = False

		#for i in range(4):
		#	new_player = player(i,None)
		#	new_controler = controlers.cpu(new_player,invisible)
		#	new_player.controler = new_controler
		#	self.players.append(new_player)

		new_player = player(0,None)
		new_controler = controlers.human_view(new_player,invisible)
		new_player.controler = new_controler
		self.players.append(new_player)

		new_player = player(1,None)
		new_controler = controlers.cpu(new_player,invisible)
		new_player.controler = new_controler
		self.players.append(new_player)

		#new_player = player(2,None)
		#new_controler = controlers.cpu(new_player,invisible)
		#new_player.controler = new_controler
		#self.players.append(new_player)

		#new_player = player(3,None)
		#new_controler = controlers.cpu(new_player,invisible)
		#new_player.controler = new_controler
		#self.players.append(new_player)

		new_player = player(2,None)
		new_controler = controlers.cpu_greedy(new_player,invisible)
		new_player.controler = new_controler
		self.players.append(new_player)


		"""new_player = player(5,None)
		new_controler = controlers.cpu_greedy(new_player,invisible)
		new_player.controler = new_controler
		self.players.append(new_player)"""


		# in range(2):
		#	new_player = player(player_id,None)
		#	new_controler = controlers.human(new_player)
		#	new_player.controler = new_controler
		#	self.players.append(new_player)




	def choose_personas(self):
		for i,p in enumerate(self.players):
			p.choose_persona(self.persona_list)
			print(f"{i} choose {p.persona.name}")
			if p.persona.name == "The Flash":
				self.whose_turn = i

	#This has not been fully adopted
	def get_current_player(self):
		if self.whose_turn == -1:
			return None
		else:
			return self.players[self.whose_turn]


	def start_game(self):
		self.dupe_checker = error_checker.dupe_checker()
		self.choose_personas()
		while self.supervillain_stack.get_count() > 0:
			self.turn_number += 1
			if self.notify != None:
				self.notify()
			if globe.DEBUG:
				print(f"{self.players[self.whose_turn].persona.name}'s' turn")

			#self.players[self.whose_turn].turn()
			current_turn = self.players[self.whose_turn]

			#Stack ongoing
			if len(self.supervillain_stack.contents) > 0 \
					and self.supervillain_stack.current_sv.has_stack_ongoing:
				self.supervillain_stack.current_sv.stack_ongoing(current_turn)

			current_turn.turn()
			#print(f"SUPER STACK:{len(self.supervillain_stack.contents)}")
			save_whose_turn = self.whose_turn
			if self.dupe_checker.check():
				return
			#It's between turns for the SV attack
			self.whose_turn = -1
			current_turn.end_turn()

			for i in range(5 - self.lineup.size()):
				card_to_add = self.main_deck.draw()
				#The main deck is empty
				if card_to_add == None:
					print("MAIN DECK RAN OUT!")
					return
				else:
					card_to_add.set_owner(owners.LINEUP)
				self.lineup.add(card_to_add)

			if self.supervillain_stack.get_count() > 0 \
					and self.supervillain_stack.current_sv != self.supervillain_stack.contents[-1]:
				self.supervillain_stack.current_sv = self.supervillain_stack.contents[-1]
				#first apearance attack

				self.supervillain_stack.current_sv.first_apearance()
				

			self.whose_turn = save_whose_turn + 1
			if self.whose_turn >= len(self.players):
				self.whose_turn = 0


			
			#with open('data.txt', 'w') as f:
			print(json.dumps(self,cls=MyEncoder))


		for p in self.players:
			#for c in p.over_superhero.contents.copy():
			#	c.destroy()
			self.player_score.append(p.calculate_vp())



	def register(self,func):
		self.notify = func


def choose_sets():
	deck_builder.choose_sets()