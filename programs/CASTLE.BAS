10 REM THE HAUNTED CASTLE
20 DIM XT(18,6),R$(18),D$(18),DK(18),OB$(18),OD$(11),OX$(11),OL(11),SR(18),F(10),TS(11),VB$(30),VV(30),DR$(12),DN$(6),SP$(6)
40 TEXT : HOME : VTAB 3: PRINT TAB(11);: INVERSE : PRINT " THE HAUNTED CASTLE ": NORMAL : PRINT
42 W$="For three hundred years the curse of Count Grimwald has held this castle in darkness. Many have entered. None have returned.": GOSUB 5000: PRINT
44 W$="Tonight you will end the curse... or join the dead.": GOSUB 5000: PRINT
46 PRINT "Type HELP for a list of commands.": PRINT "ESC returns to the agent.": PRINT : GOSUB 9000: PRINT "Press any key to begin...";
48 GET K$: IF K$ = CHR$(27) THEN TEXT : HOME : &
50 HOME : GOSUB 3000
100 PRINT : GOSUB 1000: GOSUB 2000: IF V$ = "" THEN PRINT "Pardon?": GOTO 100
110 W$=V$: GOSUB 2500: IF D THEN MV=MV+1: GOSUB 4000: GOTO 195
120 IF V$ <> "GO" AND V$ <> "WALK" AND V$ <> "RUN" THEN 130
125 W$=N$: GOSUB 2500: IF D=0 THEN PRINT "Go where?": GOTO 100
127 MV=MV+1: GOSUB 4000: GOTO 195
130 VN=0: FOR I=1 TO NV: IF V$=VB$(I) THEN VN=VV(I)
140 NEXT I
150 IF VN=0 THEN PRINT "I don't know how to do that.": GOTO 100
155 IF N$="COUN" OR N$="DRAC" THEN N$="VAMP"
160 NI=0: FOR I=1 TO 18: IF N$=OB$(I) THEN NI=I
170 NEXT I
175 MV=MV+1: GOSUB 2700
180 ON VN GOSUB 6000,6100,6200,6300,6400,6500,6600,6700,6800,6900,7000,7100,7200,7300,7400,7500,7600
190 IF WN THEN 8000
191 IF DE THEN 8500
192 IF RM <> 17 OR F(6)=0 OR F(8)=1 THEN 195
193 VT=VT+1: IF VT=3 THEN PRINT : PRINT "The vampire stirs in his sleep..."
194 IF VT >= 5 THEN DM$="The vampire's eyes snap open!": GOTO 8500
195 IF RND(1) < .08 AND RM > 2 THEN PRINT : W$=SP$( INT( RND(1)*6)+1): GOSUB 5000
199 GOTO 100
1000 REM INPUT LINE
1005 A$="": PRINT ">";
1010 GET K$:K= ASC(K$)
1020 IF K=27 THEN TEXT : HOME : &
1030 IF K=13 THEN PRINT : RETURN
1040 IF K=8 OR K=127 THEN 1100
1050 IF K >= 97 AND K <= 122 THEN K=K-32:K$= CHR$(K)
1060 IF K < 32 OR LEN(A$) >= 36 THEN 1010
1070 A$=A$+K$: PRINT K$;: GOTO 1010
1100 IF LEN(A$)=0 THEN 1010
1110 A$= LEFT$(A$, LEN(A$)-1): PRINT CHR$(8);" "; CHR$(8);: GOTO 1010
2000 REM PARSE
2005 V$="":N$=""
2010 IF A$="" THEN RETURN
2015 IF LEFT$(A$,1)=" " THEN A$= MID$(A$,2): GOTO 2010
2020 P=0: FOR I=1 TO LEN(A$): IF P=0 AND MID$(A$,I,1)=" " THEN P=I
2030 NEXT I
2040 IF P=0 THEN V$=A$: GOTO 2090
2050 V$= LEFT$(A$,P-1):N$= MID$(A$,P+1)
2060 IF LEFT$(N$,1)=" " THEN N$= MID$(N$,2): GOTO 2060
2065 IF LEFT$(N$,4)="THE " THEN N$= MID$(N$,5): GOTO 2060
2067 IF LEFT$(N$,3)="UP " THEN N$= MID$(N$,4): GOTO 2060
2070 P=0: FOR I=1 TO LEN(N$): IF P=0 AND MID$(N$,I,1)=" " THEN P=I
2080 NEXT I: IF P THEN N$= LEFT$(N$,P-1)
2090 V$= LEFT$(V$,4):N$= LEFT$(N$,4): RETURN
2500 REM DIRECTION
2505 D=0: IF W$="" THEN RETURN
2510 FOR I=1 TO 12: IF W$=DR$(I) THEN D=I
2520 NEXT I: IF D > 6 THEN D=D-6
2530 RETURN
2700 CL=1: IF DK(RM)=0 THEN RETURN
2710 CL=(F(1)=1 AND (OL(1)=99 OR OL(1)=RM)): RETURN
2800 REM IS NOUN PRESENT
2805 PR=0: IF NI=0 THEN RETURN
2810 IF NI < 12 THEN PR=(OL(NI)=99) OR (OL(NI)=RM AND CL=1): RETURN
2820 IF CL=0 OR RM <> SR(NI) THEN RETURN
2830 IF NI=15 AND F(4) THEN RETURN
2840 IF NI=17 AND (F(6)=0 OR F(8)=1) THEN RETURN
2850 PR=1: RETURN
3000 REM DESCRIBE ROOM
3005 GOSUB 2700: PRINT : INVERSE : PRINT R$(RM): NORMAL
3010 IF CL=0 THEN W$="It is pitch dark. Something with fangs could be right beside you. You need a light!": GOSUB 5000: RETURN
3020 W$=D$(RM): GOSUB 5000: GOSUB 3200
3030 FOR I=1 TO 11: IF OL(I)=RM THEN PRINT "There is ";OD$(I);" here."
3040 NEXT I
3050 E$="": FOR J=1 TO 6: IF XT(RM,J) THEN E$=E$+" "+DN$(J)
3060 NEXT J: PRINT "Exits:";E$: RETURN
3200 IF RM=4 AND F(3)=0 THEN PRINT "The oak door is shut and locked."
3205 IF RM=4 AND F(3)=1 THEN PRINT "The oak door stands open."
3210 IF RM=5 AND F(2) THEN PRINT "A rope hangs down into the well."
3220 IF RM=9 AND F(4)=0 THEN W$="A shrieking GHOST hovers on the stairs, blocking the way up!": GOSUB 5000
3230 IF RM=14 AND F(7)=0 THEN PRINT "The jewel box is closed."
3235 IF RM=14 AND F(7)=1 THEN PRINT "The jewel box is open."
3240 IF RM=15 AND F(5) THEN PRINT "A secret stair leads down behind the altar."
3250 IF RM=17 AND F(6)=0 THEN PRINT "The coffin lid is closed."
3255 IF RM=17 AND F(6)=1 AND F(8)=0 THEN W$="The coffin is open. A VAMPIRE sleeps inside!": GOSUB 5000
3257 IF RM=17 AND F(8)=1 THEN PRINT "A pile of dust lies in the coffin."
3260 RETURN
4000 REM MOVE
4005 T=XT(RM,D): IF T THEN RM=T: GOSUB 3000: RETURN
4010 IF RM=4 AND D=4 THEN PRINT "The oak door is locked tight.": RETURN
4020 IF RM=9 AND D=5 THEN W$="The ghost shrieks and hurls you back down the stairs! It seems to fear holy things.": GOSUB 5000: RETURN
4030 IF RM=5 AND D=6 THEN W$="The well is far too deep to climb down without a rope.": GOSUB 5000: RETURN
4040 PRINT "You can't go that way.": RETURN
5000 REM WORD WRAP W$
5005 IF LEN(W$) < 40 THEN PRINT W$: RETURN
5010 P=41
5020 P=P-1: IF P > 1 AND MID$(W$,P,1) <> " " THEN 5020
5030 IF P <= 1 THEN PRINT LEFT$(W$,39):W$= MID$(W$,40): GOTO 5005
5040 PRINT LEFT$(W$,P-1):W$= MID$(W$,P+1): GOTO 5005
6000 REM GET
6005 IF N$="" THEN PRINT "Get what?": RETURN
6010 IF CL=0 THEN PRINT "You fumble around in the dark.": RETURN
6020 IF NI=0 THEN PRINT "I don't see that here.": RETURN
6030 IF NI > 11 THEN GOSUB 2800: IF PR THEN PRINT "You can't carry that!": RETURN
6035 IF NI > 11 THEN PRINT "I don't see that here.": RETURN
6040 IF OL(NI)=99 THEN PRINT "You already have it.": RETURN
6050 IF OL(NI) <> RM THEN PRINT "I don't see that here.": RETURN
6060 OL(NI)=99: PRINT "Taken."
6070 IF NI >= 8 AND TS(NI)=0 THEN TS(NI)=1:SC=SC+10: PRINT "A treasure! (+10 points)"
6080 RETURN
6100 REM DROP
6105 IF N$="" THEN PRINT "Drop what?": RETURN
6110 IF NI=0 OR NI > 11 THEN PRINT "You don't have that.": RETURN
6120 IF OL(NI) <> 99 THEN PRINT "You don't have that.": RETURN
6130 OL(NI)=RM: PRINT "Dropped.": RETURN
6200 REM INVENTORY
6205 PRINT "You are carrying:":C=0
6210 FOR I=1 TO 11: IF OL(I) <> 99 THEN 6230
6220 W$="  "+OD$(I): IF I=1 AND F(1) THEN W$=W$+" (lit)"
6225 PRINT W$:C=C+1
6230 NEXT I
6240 IF C=0 THEN PRINT "  nothing at all."
6250 RETURN
6300 REM LOOK
6305 IF N$ <> "" THEN 6400
6310 GOSUB 3000: RETURN
6400 REM EXAMINE
6405 IF N$="" THEN PRINT "Examine what?": RETURN
6410 GOSUB 2800: IF PR=0 THEN PRINT "I don't see that here.": RETURN
6420 IF NI < 12 THEN W$=OX$(NI): GOSUB 5000: IF NI=1 AND F(1) THEN PRINT "It is burning brightly."
6425 IF NI < 12 THEN RETURN
6430 ON NI-11 GOTO 6440,6450,6460,6470,6480,6490,6495
6440 PRINT "A small carved ebony jewel box.": IF F(7) THEN PRINT "It is open.": RETURN
6445 PRINT "It is closed.": RETURN
6450 W$="A crumbling stone well. A cold draft rises from far below.": GOSUB 5000: IF F(2) THEN PRINT "Your rope hangs down into it."
6455 RETURN
6460 PRINT "A massive oak door bound with iron.": IF F(3)=0 THEN PRINT "It is locked. It has a big keyhole."
6465 RETURN
6470 W$="A pale howling figure in rotted finery. It glares at you with burning eyes.": GOSUB 5000: RETURN
6480 PRINT "A great black coffin, silver handled.": RETURN
6490 W$="Count Grimwald himself, pale as death, with blood on his lips. He sleeps... for now.": GOSUB 5000: RETURN
6495 W$="Runes are carved into the stone. They seem to spell a word, but they are too worn to read.": GOSUB 5000: RETURN
6500 REM READ
6505 IF N$="" THEN PRINT "Read what?": RETURN
6510 GOSUB 2800: IF PR=0 THEN PRINT "I don't see that here.": RETURN
6520 IF NI=18 THEN 6495
6530 IF NI <> 5 THEN PRINT "There's nothing written on it.": RETURN
6540 W$="The book falls open to a page marked in blood:": GOSUB 5000
6550 W$="'To open the hidden way, speak the word MORTIS before the altar.'": GOSUB 5000
6560 W$="Below, in another hand: 'The Count sleeps beneath. Only wood through the heart will end him.'": GOSUB 5000: RETURN
6600 REM LIGHT
6605 IF N$="" THEN NI=1
6607 IF NI <> 1 AND NI <> 2 THEN PRINT "You can't light that.": RETURN
6610 IF OL(1) <> 99 THEN PRINT "You aren't carrying the lamp.": RETURN
6620 IF F(1) THEN PRINT "The lamp is already lit.": RETURN
6630 IF OL(2) <> 99 THEN PRINT "You have nothing to light it with.": RETURN
6640 F(1)=1:SC=SC+10:W$="You strike a match and light the lamp. A warm glow surrounds you. (+10)": GOSUB 5000
6650 IF DK(RM) THEN GOSUB 3000
6660 RETURN
6700 REM TIE
6705 IF NI <> 3 THEN PRINT "You can't tie that.": RETURN
6710 IF OL(3) <> 99 THEN PRINT "You don't have the rope.": RETURN
6720 IF RM <> 5 THEN PRINT "There's nothing here to tie it to.": RETURN
6730 F(2)=1:OL(3)=0:XT(5,6)=10:SC=SC+10
6740 W$="You tie the rope to the well and lower it into the darkness. (+10)": GOSUB 5000: RETURN
6800 REM OPEN / UNLOCK
6805 IF N$="" THEN PRINT "Open what?": RETURN
6810 GOSUB 2800: IF PR=0 THEN PRINT "I don't see that here.": RETURN
6820 IF NI=14 THEN 6850
6830 IF NI=12 THEN 6870
6840 IF NI=16 THEN 6890
6845 PRINT "You can't open that.": RETURN
6850 IF F(3) THEN PRINT "It's already open.": RETURN
6855 IF OL(4) <> 99 THEN PRINT "It's locked. You need a key.": RETURN
6860 F(3)=1:XT(4,4)=8:SC=SC+10:W$="The iron key turns with a screech and the oak door swings open! (+10)": GOSUB 5000: RETURN
6870 IF F(7) THEN PRINT "It's already open.": RETURN
6875 F(7)=1:OL(10)=RM: PRINT "Inside the jewel box is a ruby ring!": RETURN
6890 IF F(6) THEN PRINT "It's already open.": RETURN
6895 F(6)=1:VT=0:W$="You heave the heavy lid aside. Inside lies a VAMPIRE, pale and still, in deathly sleep!": GOSUB 5000: RETURN
6900 REM SHOW / WAVE
6905 IF NI <> 6 THEN PRINT "Nothing happens.": RETURN
6910 IF OL(6) <> 99 THEN PRINT "You don't have the cross.": RETURN
6920 IF RM=9 AND F(4)=0 THEN F(4)=1:XT(9,5)=12:SC=SC+10:W$="You raise the silver cross. The ghost shrieks in terror and dissolves into mist! The way up is clear. (+10)": GOSUB 5000: RETURN
6930 IF RM=17 AND F(6)=1 AND F(8)=0 THEN PRINT "The vampire hisses in his sleep.": RETURN
6940 PRINT "The cross glints. Nothing happens.": RETURN
7000 REM SAY
7005 IF N$="" THEN PRINT "Say what?": RETURN
7010 IF N$ <> "MORT" THEN PRINT "You say it. Nothing happens.": RETURN
7020 IF RM <> 15 THEN PRINT "The word echoes eerily. Nothing happens.": RETURN
7030 IF F(5) THEN PRINT "Nothing more happens.": RETURN
7040 F(5)=1:XT(15,6)=18:SC=SC+10:W$="The runes blaze with light! With a grinding roar the altar slides aside, revealing a secret stair. (+10)": GOSUB 5000: RETURN
7100 REM KILL
7105 IF N$="" THEN PRINT "Kill what?": RETURN
7110 GOSUB 2800: IF PR=0 THEN PRINT "I don't see that here.": RETURN
7120 IF NI=15 THEN PRINT "Your blows pass right through it!": RETURN
7130 IF NI <> 17 THEN PRINT "Violence won't help here.": RETURN
7140 IF OL(7)=99 THEN F(8)=1:SC=SC+10:WN=1: RETURN
7150 DE=1:DM$="You attack the vampire with your bare hands. His eyes snap open!": RETURN
7200 PRINT "Score: ";SC;" of 100 in ";MV;" moves.": RETURN
7300 W$="Type commands like GET LAMP, OPEN DOOR or GO NORTH. Move with N S E W U D.": GOSUB 5000
7310 W$="Verbs: GET DROP LOOK EXAMINE READ LIGHT TIE OPEN UNLOCK SHOW WAVE SAY KILL USE CLIMB INVENTORY SCORE QUIT": GOSUB 5000
7320 PRINT "ESC returns to the agent.": RETURN
7400 PRINT "Really quit (Y/N)? ";: GET K$:K= ASC(K$): PRINT K$: IF K=89 OR K=121 THEN TEXT : HOME : &
7410 RETURN
7500 IF RM=5 THEN D=6: GOSUB 4000: RETURN
7510 IF RM=10 THEN D=5: GOSUB 4000: RETURN
7520 PRINT "There's nothing to climb here.": RETURN
7600 REM USE
7605 IF N$="" THEN PRINT "Use what?": RETURN
7610 IF NI=0 OR NI > 11 THEN PRINT "You can't use that.": RETURN
7615 IF OL(NI) <> 99 THEN PRINT "You don't have that.": RETURN
7620 IF NI=1 OR NI=2 THEN 6600
7630 IF NI=3 THEN 6700
7640 IF NI=4 AND RM <> 4 THEN PRINT "There's nothing here to unlock.": RETURN
7645 IF NI=4 THEN NI=14: GOTO 6800
7650 IF NI=5 THEN 6500
7660 IF NI=6 THEN 6900
7670 IF NI=7 AND RM <> 17 THEN PRINT "There's nothing here to use it on.": RETURN
7675 IF NI=7 THEN NI=17: GOTO 7100
7680 PRINT "Nothing happens.": RETURN
8000 PRINT :W$="You plunge the stake into the vampire's heart! Count Grimwald screams and crumbles to dust.": GOSUB 5000
8010 W$="All through the castle the ghosts sigh and fade away. Dawn breaks over Castle Grimwald. The curse is lifted!": GOSUB 5000
8020 PRINT : INVERSE : PRINT " *** YOU HAVE WON! *** ": NORMAL : GOTO 8600
8500 PRINT :W$=DM$: GOSUB 5000
8510 W$="Before you can scream, cold fangs find your throat. You will serve Count Grimwald forever...": GOSUB 5000
8520 PRINT : INVERSE : PRINT " *** YOU HAVE DIED *** ": NORMAL
8600 PRINT "You scored ";SC;" of 100 in ";MV;" moves.":T=0: FOR I=8 TO 11:T=T+TS(I): NEXT I: PRINT "Treasures found: ";T;" of 4"
8610 PRINT : PRINT "Play again (Y/N)? ";
8620 GET K$:K= ASC(K$): IF K=89 OR K=121 THEN 40
8630 IF K=78 OR K=110 OR K=27 THEN TEXT : HOME : &
8640 GOTO 8620
9000 REM INITIALIZE
9005 RESTORE
9010 FOR R=1 TO 18: READ R$(R),D$(R),DK(R): FOR J=1 TO 6: READ XT(R,J): NEXT J,R
9020 FOR I=1 TO 11: READ OB$(I),OD$(I),OL(I),OX$(I):TS(I)=0: NEXT I
9030 FOR I=12 TO 18: READ OB$(I),SR(I): NEXT I
9040 NV=0
9050 NV=NV+1: READ VB$(NV),VV(NV): IF VB$(NV) <> "END" THEN 9050
9060 NV=NV-1: FOR I=1 TO 12: READ DR$(I): NEXT I: FOR I=1 TO 6: READ DN$(I): NEXT I: FOR I=1 TO 6: READ SP$(I): NEXT I
9070 FOR I=1 TO 10:F(I)=0: NEXT I:SC=0:MV=0:RM=1:WN=0:DE=0:VT=0: RETURN
9100 DATA "DRAWBRIDGE","You stand on a rotting drawbridge before Castle Grimwald. Black towers claw at a stormy sky. The castle gate lies open to the north.",0
9101 DATA 2,0,0,0,0,0
9102 DATA "GATEHOUSE","A cramped guardroom. Rusty pikes line the walls and a skeleton slumps in the corner, still on duty.",0
9103 DATA 3,1,0,0,0,0
9104 DATA "COURTYARD","A weedy courtyard open to the rain. The great hall lies north, a garden east and the stables west.",0
9105 DATA 4,2,5,6,0,0
9106 DATA "GREAT HALL","A vast hall hung with tattered banners. Portraits with moving eyes watch you. A heavy oak door is set in the west wall.",0
9107 DATA 9,3,7,0,0,0
9108 DATA "GARDEN","A dead garden of black roses. An old stone well sits in the middle, its depths lost in darkness.",0
9109 DATA 0,0,0,3,0,0
9110 DATA "STABLES","Empty stalls smell of old straw. Something unseen whinnies softly, then falls silent.",0
9111 DATA 0,0,3,0,0,0
9112 DATA "DINING HALL","A long table is set for a feast that rotted centuries ago. Candles burn with cold blue flames.",0
9113 DATA 11,0,0,4,0,0
9114 DATA "LIBRARY","Shelves of crumbling books rise into shadow. A reading desk stands by a cold fireplace.",0
9115 DATA 0,0,4,0,0,0
9116 DATA "GRAND STAIR","A sweeping marble staircase climbs into the gloom above.",0
9117 DATA 0,4,0,0,0,0
9118 DATA "BOTTOM OF THE WELL","You stand ankle deep in icy water at the bottom of the well. Slimy walls rise all around.",1
9119 DATA 0,0,0,0,5,0
9120 DATA "KITCHEN","Copper pots hang over a huge hearth. A trapdoor in the floor leads down.",0
9121 DATA 0,7,0,0,0,13
9122 DATA "UPPER LANDING","A drafty landing. Doors lead east and west, a narrow stair winds north into a tower, and the grand stair leads down.",0
9123 DATA 16,0,14,15,0,9
9124 DATA "WINE CELLAR","Racks of dusty bottles fill this damp cellar. Something skitters behind the casks.",1
9125 DATA 0,0,0,0,11,0
9126 DATA "BEDCHAMBER","A canopied bed draped in cobwebs. One bedpost has been snapped off. A jewel box sits on the dresser.",0
9127 DATA 0,0,0,12,0,0
9128 DATA "CHAPEL","A ruined chapel. Moonlight falls through broken stained glass onto a stone altar carved with runes.",0
9129 DATA 0,0,12,0,0,0
9130 DATA "TOWER TOP","Wind howls around the battlements. Far below, the moat glimmers. Ravens watch you from the parapet.",0
9131 DATA 0,12,0,0,0,0
9132 DATA "CRYPT","A freezing crypt lined with ancient tombs. In the center rests a great black coffin.",1
9133 DATA 0,0,0,0,18,0
9134 DATA "SECRET STAIR","A narrow hidden stair spirals down through the stone, slick with damp.",1
9135 DATA 0,0,0,0,15,17
9200 DATA "LAMP","a brass lamp",2,"An old brass oil lamp, full of oil."
9201 DATA "MATC","a box of matches",11,"A small box of dry matches."
9202 DATA "ROPE","a coil of rope",6,"Strong hemp rope, about fifty feet long."
9203 DATA "KEY","an iron key",10,"A heavy iron key, black with age."
9204 DATA "BOOK","a dusty spellbook",8,"A spellbook bound in cracked leather. Perhaps you should READ it."
9205 DATA "CROS","a silver cross",8,"A silver cross. It glows with a faint, holy light."
9206 DATA "STAK","a wooden stake",14,"A sharp wooden stake - the broken end of a bedpost."
9207 DATA "GOBL","a jeweled goblet",13,"A golden goblet crusted with emeralds. A treasure!"
9208 DATA "CROW","a golden crown",16,"The crown of the old kings of Grimwald. A treasure!"
9209 DATA "RING","a ruby ring",0,"A ring set with a ruby as red as blood. A treasure!"
9210 DATA "GEM","a glowing gem",15,"A gem that pulses with an eerie inner light. A treasure!"
9300 DATA "BOX",14,"WELL",5,"DOOR",4,"GHOS",9,"COFF",17,"VAMP",17,"ALTA",15
9400 DATA "GET",1,"TAKE",1,"PICK",1,"DROP",2,"INVE",3,"I",3,"INV",3,"LOOK",4,"L",4,"EXAM",5,"X",5,"READ",6,"LIGH",7,"TIE",8,"UNLO",9,"OPEN",9
9410 DATA "SHOW",10,"WAVE",10,"HOLD",10,"SAY",11,"KILL",12,"STAB",12,"ATTA",12,"SCOR",13,"HELP",14,"QUIT",15,"CLIM",16,"USE",17,"END",0
9500 DATA "N","S","E","W","U","D","NORT","SOUT","EAST","WEST","UP","DOWN"
9510 DATA "north","south","east","west","up","down"
9600 DATA "A cold wind blows out of nowhere, then is gone.","Somewhere far away, a woman screams.","You hear chains rattling inside the walls.","A bat flutters past your head."
9610 DATA "Thunder booms. For an instant you see a shadow behind you.","An organ plays a few mournful notes, then stops."
