// "Signal Fire" — a sample cartridge for the chat-sim engine.
// Shows: waits (real-time gaps -> notifications), a loop with an exit,
// two paths that converge on the same knot, a tunnel, and three endings.

// Global tags: read once by the engine at load.
// Timing rule: "# wait: 10m" delays the message it is attached to (the character was away).
// "# presence: busy" on a message shows the character as away after it is sent.
# title: Signal Fire
# author: Example
# chat: wren

EXTERNAL player_name()
EXTERNAL local_hour()

VAR trust = 0
VAR battery = 9
VAR lamp_lit = false
VAR tried_radio = 0

-> opening

=== opening ===
# speaker: wren
hello?? is this the coastguard
please say this is the coastguard
* [Wrong number, sorry]
    no no no. ok. sorry
    ~ trust = trust - 1
* [Who is this?]
    ~ trust = trust + 1
    my name's Wren. I keep the light on Skerry Isle
    or I did until about an hour ago
- the storm took the radio mast. this phone is all I have # typing: 4s
it's on {battery}% # image: battery_low.png
-> the_lamp

=== the_lamp ===
the lamp's dark. ships use it to find the channel
* [Can you fix it?]
    maybe. the generator's in the shed
* [Is anyone out there tonight?]
    ~ trust = trust + 1
    a trawler. I saw its lights before the lamp went out
    so yeah. someone's out there
- I'm going to try the radio one more time first. back soon # presence: busy
-> radio_loop

// A loop: the player can keep asking Wren to retry the radio.
// It always exits, because the third try forces the choice away.
=== radio_loop ===
~ tried_radio++
~ battery = battery - 1
# wait: 10m
{tried_radio == 1: nothing. just static|{tried_radio == 2: static again. and something like a voice? gone now|dead. the set's dead}}
+ {tried_radio < 3} [Try once more]
    ok. once more # presence: busy
    -> radio_loop
* [Forget the radio. The lamp matters more]
    -> to_the_shed
* {trust >= 1} [{player_name()} says: you've got this. go]
    ~ trust = trust + 1
    ha. ok, {player_name()}. going
    -> to_the_shed

// Convergence: both shed choices above (and the loop's exits) arrive here.
=== to_the_shed ===
going out to the shed. the wind is unreal # presence: busy
# wait: 25m
-> shed_report ->
{
- lamp_lit: -> beacon
- else: -> in_the_dark
}

// A tunnel: used by one route, returns to the caller.
=== shed_report ===
made it. soaked through
the generator's flooded but the spare battery bank looks ok
* [Wire the battery to the lamp]
    ~ lamp_lit = true
    doing it. hands are shaking # presence: busy
    ->->
* [Get back inside where it's safe]
    ~ trust = trust - 1
    yeah. you're right. heading back # presence: busy
    ->->

=== beacon ===
# wait: 5m
IT'S ON
the light's turning. I can see the beam on the water
* [Watch for the trawler]
    # wait: 15m
    -> trawler
* [Get some rest, you earned it]
    # wait: 2h
    I slept by the lamp. phone's on {battery - 3}%
    // Time checks go on the line AFTER a wait: the clock moves when the waited line is delivered
    {local_hour() >= 6 && local_hour() < 20: it's light out now|still dark out}
    -> trawler

=== trawler ===
{trust >= 2:
    -> ending_saved
- else:
    -> ending_alone
}

=== in_the_dark ===
# wait: 5m
I'm back inside. the lamp's still dark
* [Go back out and try again]
    -> to_the_shed
* [Wait for daylight]
    # wait: 3h
    -> ending_dark

=== ending_saved ===
the trawler's turning into the channel. they're signalling me. they made it
{player_name()}. thank you for answering a wrong number
# ending: saved
-> END

=== ending_alone ===
the trawler made it in. nobody knows I'm here though
phone's nearly dead. bye
# ending: alone
-> END

=== ending_dark ===
light's coming up. no sign of the trawler
I don't want to talk any more
# ending: dark
-> END
