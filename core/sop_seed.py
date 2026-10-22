"""The first draft of the SOP file – written from what the Manager told us (18 Oct 2026).

Job titles only, never names, so the file can be used in other shops too. Every SOP starts as a Draft; the
Manager reads and changes it in Pondo, and the Owner / Director approves it.
Loaded once by migration 0014; after that the SOPs live in the database and are changed in Pondo.

applies: department keys from staff.models.DEPARTMENTS, or "all".
"""

SECTIONS = [
    (1, "Opening & closing"),
    (2, "Cash, tills & cash-up"),
    (3, "Production & baking"),
    (4, "Food safety & hygiene"),
    (5, "Stock, orders & receiving"),
    (6, "Customer service & sales"),
    (7, "Staff & HR"),
    (8, "Health, safety & emergencies"),
]

S = []


def sop(section, title, applies, responsible, purpose, body):
    S.append({"section": section, "title": title, "applies": applies, "responsible": responsible,
              "purpose": purpose, "body": body.strip()})


# ======================================================================= 1 OPENING & CLOSING
sop(1, "Opening the shop", "shop,production,security,admin", "Day Supervisor · Night Supervisor (Sunday night)",
    "Open the shop safely, on time and ready to trade at 06:00 (Monday – Saturday).", """
<h3>Times</h3>
<ul><li>Monday – Friday: shop opens <b>06:00</b>, closes <b>19:00</b>.</li>
<li>Saturday: opens <b>06:00</b>, closes <b>16:00</b>.</li>
<li>Sundays and public holidays: <b>closed</b>.</li></ul>
<h3>Monday – Saturday morning</h3>
<ol>
<li>The Day Supervisor arrives at <b>05:45</b>. The Night Supervisor unlocks the staff door for the day staff – the front door stays locked.</li>
<li>Take over from the Night Supervisor (see SOP “Night shift start &amp; hand-over”) and read the <b>hand-over book</b>.</li>
<li>Walk through the shop, the bakery, the walk-in fridge and the walk-in deep freezer: lights, power, water, fridges and freezers running, no leaks, no signs of pests.</li>
<li>Write the morning <b>fridge and freezer temperatures</b> on the temperature log.</li>
<li>Check that every day staff member on the roster has clocked in, is in full uniform and is fit to work. Phone the Manager about anybody missing.</li>
<li>Give each cashier their till float (see SOP “Starting a till &amp; the float”).</li>
<li>Counter staff fill the shelves and display with <b>today's</b> products, oldest at the front, and remove anything past its sell-by date (see SOP “Daily shop floor rotation”).</li>
<li>Check the shop floor is clean, the price cards are right and the till slips, bags and boxes are stocked.</li>
<li>At 06:00 unlock the front door and open.</li>
</ol>
<h3>Sunday 19:00 – opening the building after the weekend</h3>
<ol>
<li>The Night Supervisor arrives with at least one other night-shift staff member – <b>never alone</b>.</li>
<li>Check the outside first: doors, windows, locks and roller doors. Anything broken or forced? <b>Do not go in</b> – phone the Manager and the police.</li>
<li>Go in, lock the door behind you, and walk through the whole building: power, water, fridge and freezer temperatures, leaks, pests.</li>
<li>Write what you found in the hand-over book, then start the night shift.</li>
</ol>
<h3>Never</h3>
<ul><li>Never open the building alone.</li>
<li>Never let anybody in before opening time except staff on the roster.</li></ul>
""")

sop(1, "Closing the shop", "shop,production,security,admin", "Day Supervisor (Supervisor on duty)",
    "Close the shop safely, with all money accounted for, the shop clean and the building handed over or locked.", """
<h3>Monday – Friday, 19:00</h3>
<ol>
<li><b>15 minutes before closing</b>: tell staff to start the closing clean. Stop putting out new products.</li>
<li>At 19:00 lock the front door. Let the last customers out; nobody else comes in.</li>
<li>Counter staff take products off the display: what may still be sold tomorrow (check the label) goes into the right storage; what has expired is logged as <b>waste</b> (see SOP “Logging waste”).</li>
<li>Every cashier does the <b>cash-up</b> of their till with the Supervisor (see SOP “Cash-up and over / short”).</li>
<li>The cash is sealed in a cash bag with the cash-up slip and handed to the <b>manager on duty</b>, who locks it in the safe. Only managers have the safe key.</li>
<li>Check that the closing clean is done in the shop and the toilets. Write the evening <b>fridge and freezer temperatures</b> on the log.</li>
<li>After the <b>last cash-up</b>: the Supervisor or Manager makes the <b>daily backup</b> on the flash drive (see SOP “Daily backup”).</li>
<li>Switch off display lights, tills and machines not used by the night shift. Fridges and freezers stay <b>on</b>.</li>
<li>Hand the building over to the Night Supervisor and write it in the <b>hand-over book</b> (see SOP “Night shift start &amp; hand-over”).</li>
<li>Day staff leave through the staff door after the bag check. The Night Supervisor locks it behind them.</li>
</ol>
<h3>Saturday, 16:00</h3>
<ol>
<li>The weekly clean is done <b>from 13:00 to 16:00</b>, while the shop is still open, so that nobody has to stay behind after 16:00 (see SOP “Clean as you go &amp; end-of-shift cleaning”).</li>
<li>At 16:00 lock the front door, take products off the display and log the waste.</li>
<li>Cash-up of every till with the Supervisor – then the <b>daily backup</b> on the flash drive (see SOP “Daily backup”).</li>
<li>The takings are sealed in cash bags with the cash-up slips and handed to a <b>manager</b> (see SOP “Safe and cash collection”).</li>
<li>Write the temperatures. Switch off everything except the fridges and freezers. Close all taps.</li>
<li>Check <b>every</b> door, window, the back door and the roller doors yourself.</li>
<li>Everybody leaves together after the bag check. Lock all doors and the gate and check them once more.</li>
</ol>
<h3>Never</h3>
<ul><li>Never leave money in a till drawer.</li>
<li>Never lock up alone – the Supervisor and at least one other staff member leave together.</li></ul>
""")

sop(1, "Night shift start & hand-over", "production,admin", "Night Supervisor and Day Supervisor",
    "Make sure nothing is forgotten between the day shift and the night shift – both ways – and that the building is safe at night.", """
<h3>Night shift times</h3>
<ul><li>Night shift works <b>19:00 to 07:00</b> the next morning, Sunday night to Friday night.</li>
<li>There is <b>no night shift on Saturday night</b>.</li></ul>
<h3>The hand-over book</h3>
<p>A hard-cover book kept in the bakery office. At every hand-over the Supervisor going off duty writes:</p>
<ul><li>Date, shift and time of the hand-over.</li>
<li>What was made against the production plan, and what was not made and why.</li>
<li>Special and bulk orders for the next shift.</li>
<li>Breakdowns, power cuts (times off and on), accidents and injuries, visitors, anything strange.</li>
<li>Stock that ran out or is running low.</li>
<li>Keys handed over.</li></ul>
<p>Both Supervisors sign. The Manager reads the book every morning.</p>
<h3>Evening hand-over (Day Supervisor → Night Supervisor, 19:00)</h3>
<ol>
<li>The Night Supervisor checks that the night shift has clocked in, is in full uniform and is fit to work.</li>
<li>The Day Supervisor hands over the keys, the production plan for the night (printed from Pondo) and the orders for tomorrow.</li>
<li>Both walk through the bakery: clean, ovens and machines working, ingredients for the night ready.</li>
<li>Both write and sign the hand-over book.</li>
</ol>
<h3>At night</h3>
<ul><li>When the day staff have left, the Night Supervisor locks <b>every</b> door. Doors stay locked all night.</li>
<li><b>Nobody</b> is let in at night – no visitors, no deliveries, no ex-staff, nobody “sent by the manager”. If somebody says the Manager sent them, phone the Manager first.</li>
<li>Night staff don't go outside during the shift. Rubbish goes out in the morning.</li>
<li>Anything suspicious: don't open – phone the Manager and the police.</li></ul>
<h3>Morning hand-over (Night Supervisor → Day Supervisor, 07:00)</h3>
<ol>
<li>The Night Supervisor makes sure the night shift has cleaned the bakery and logged its waste.</li>
<li>The production plan is marked <b>Done</b> in Pondo.</li>
<li>Both write and sign the hand-over book. Only then may the night shift clock out and leave, after the bag check by Security.</li>
</ol>
""")

sop(1, "Daily backup", "shop,admin", "Supervisor on duty · Manager · Assistant Manager",
    "Never lose the day's work: every trading day ends with a backup of Pondo on the flash drive.", """
<h3>When</h3>
<ul><li><b>Every trading day</b>, straight after the <b>last cash-up</b> of the day (Monday – Friday after 19:00, Saturday after 16:00).</li>
<li>Pondo asks for it: after a cash-up is saved a screen pops up – <i>“Last cash-up of the day? … Back up now”</i>.</li></ul>
<h3>How</h3>
<ol>
<li>Make sure <b>every till is cashed up</b> and signed off.</li>
<li>Plug the <b>flash drive</b> into the main computer and wait a few seconds.</li>
<li>In Pondo press <b>Back up now</b> (menu, <i>Help &amp; settings</i>, or the pop-up) and choose the flash drive.</li>
<li>Wait for <b>“Backup saved on the flash drive”</b>. Then take the flash drive out.</li>
<li>Keep the flash drive <b>locked away</b>, not next to the computer – it holds staff papers and all the figures.</li>
</ol>
<h3>No backup – no start</h3>
<ul><li>If the last trading day's cash-ups were <b>not</b> backed up, <b>Pondo is locked the next morning</b> for everybody. It shows <i>“Make the backup first”</i> until the Supervisor or Manager makes it.</li>
<li>Only the Supervisors, the Assistant Manager and the Manager can make the backup.</li>
<li>Flash drive lost or broken? Only the <b>Manager</b> can open Pondo for that day without the backup, with a written reason. A new flash drive is bought the same day.</li></ul>
""")

# ======================================================================= 2 CASH
sop(2, "Starting a till & the float", "shop,admin", "Supervisor on duty · Cashiers",
    "Every till starts the day with a counted float that the cashier agrees to.", """
<ol>
<li>Every till starts with a float of <b>US$200</b> in small notes and coins. The manager takes the float bags out of the safe and gives each cashier the float for their till (Till 1 or Till 2).</li>
<li>The cashier and the manager <b>count it together</b>, note for note and coin for coin.</li>
<li>Both write the amount, the till and the time on the float sheet and sign.</li>
<li>The cashier logs in on the till with <b>their own</b> code. Never use somebody else's code.</li>
<li>From now on the cashier is responsible for that drawer until the cash-up. Nobody else works on your till.</li>
</ol>
<h3>Rules at the till</h3>
<ul><li>Ring up <b>every</b> sale and give every customer a slip.</li>
<li>Close the drawer after every sale.</li>
<li>Check big notes (US$50, US$100) for forgeries. In doubt: call the Supervisor.</li>
<li>Leaving the till, even for a minute: log out or lock it.</li>
<li>No personal money, phones or bags at the till.</li></ul>
""")

sop(2, "Cash drops to the safe", "shop,admin", "Manager on duty · Cashiers",
    "Keep as little cash as possible in the tills during the day.", """
<ol>
<li>When a till has more than <b>US$500</b> in cash, the cashier calls the <b>manager on duty</b> – only managers have the safe key.</li>
<li>The manager and the cashier count the drop together, away from customers. Leave the float in the till.</li>
<li>Write a <b>drop slip</b>: date, time, till, amount, both signatures.</li>
<li>Put the money and the slip in a cash bag, seal it, and the manager locks it in the <b>safe</b> straight away.</li>
<li>Write the drop on the cash-up in Pondo under the cash taken to the safe.</li>
</ol>
<h3>Never</h3>
<ul><li>Only the <b>managers</b> (Manager, Assistant Manager) and the <b>Owner / Director</b> open the safe. Nobody else ever has the key.</li>
<li>Never count money in front of customers or leave a cash bag lying around – not even for a minute.</li></ul>
""")

sop(2, "Pay-outs from the till", "shop,admin", "Supervisor on duty",
    "Money taken out of a till is always approved, signed for and recorded.", """
<ol>
<li>Pay-outs (gas, transport, small purchases) need the <b>Supervisor's approval</b> first.</li>
<li>Get a receipt or slip from the person or shop that was paid.</li>
<li>The person who takes the money signs the pay-out slip with the amount, the reason and the date.</li>
<li>Keep the slip in the drawer and type the pay-out on the cash-up in Pondo (<i>+ Add pay-out</i>) – what it was for, who got it, the amount and the slip number.</li>
</ol>
<p>Stock bought from a supplier is never paid from the till without the Manager's approval – it goes on a GRV.</p>
""")

sop(2, "Cash-up and over / short", "shop,admin", "Cashier · Supervisor on duty · Manager",
    "Every till is cashed up at the end of every shift, honestly, and differences are explained.", """
<ol>
<li>Print the till's end-of-day (<b>Z</b>) report.</li>
<li>The cashier counts the drawer <b>with the Supervisor watching</b>: notes and coins, the float included, ZiG notes separately.</li>
<li>In Pondo: <b>Sales &amp; Cash-Up → Cash-ups</b> → date, till and the cashier's name → <i>Start cash-up</i>. Type what the till says per payment type, the pay-outs and the cash counted.</li>
<li>Pondo shows <b>over</b> or <b>short</b>. If it is not zero: count again before saving.</li>
<li>Still over or short: write what happened in the notes. Never “fix” the numbers.</li>
<li>Save, print the cash-up slip and put it in the bag with the cash.</li>
<li>The Supervisor checks and presses <b>Sign off</b> in Pondo.</li>
<li>When the <b>last till</b> of the day is cashed up, Pondo asks for the <b>daily backup</b> – the Supervisor or Manager makes it straight away (see SOP “Daily backup”).</li>
</ol>
<h3>Shorts and overs</h3>
<ul><li><b>Shorts are paid by the cashier.</b> Overs do <b>not</b> cancel out shorts – every short counts on its own.</li>
<li><b>Overs</b> are sealed in a bag with the cash-up slip and placed in the <b>safe the same day</b> by the manager. Overs are never taken home, used or paid out to the cashier.</li>
<li>If there is a <b>logical, reasonable explanation</b> for a short (e.g. a proven till or card-machine error), the manager may <b>write it off</b>. The reason is written on the cash-up and signed by the manager.</li>
<li>At <b>month end</b> the Manager prints the <i>Over &amp; short per cashier</i> report from Pondo, goes through it with each cashier, and both sign it. The month's shorts (less any written off) are paid by the cashier as agreed in the <b>employment contract</b>.</li>
<li>This only applies to cashiers whose signed contract has the cash-shortage clause – a deduction from pay needs the worker's written agreement.</li>
<li>Repeated or large shorts are also handled under the disciplinary code.</li></ul>
""")

sop(2, "Safe and cash collection", "admin", "Manager · Owner / Director",
    "Keep the takings safe until they are collected or banked.", """
<ul><li>Only the <b>managers</b> (Manager, Assistant Manager) and the <b>Owner / Director</b> have the safe key.</li>
<li>Every cash bag is handed to a manager, who locks it in the safe straight away.</li>
<li>When the safe is opened, a <b>second person</b> watches. Every bag is checked against its cash-up slip.</li>
<li>Collection and banking of the takings are arranged by the <b>Owner / Director</b> with the Manager only. When, how and by whom money is collected is <b>never written down in this file</b>, discussed or told to anybody.</li>
<li>Every collection is written in the safe book: date, bags, amount, both signatures. The safe book is kept locked away.</li>
<li>Never talk about the takings, the safe, cash amounts or collection times – not to colleagues, family, friends or on social media.</li></ul>
""")

sop(2, "Payday – salary envelopes", "all", "Manager · Owner / Director",
    "Pay every staff member the right amount in cash, safely and signed for.", """
<ol>
<li>Payday is the <b>last working day of the month</b>.</li>
<li>The pay run is made <b>final</b> in Pondo and the payslips are printed.</li>
<li>The Manager counts each person's net pay into an envelope <b>with a second person watching</b>, and puts the payslip in it. Write the name and staff number on the envelope and seal it.</li>
<li>Pay out in the office, one person at a time. The staff member opens the envelope and counts the money <b>in front of the Manager</b>.</li>
<li>The staff member signs the pay sheet. Problems must be raised <b>before signing</b>.</li>
<li>Envelopes not collected go back into the safe and are written in the safe book.</li>
</ol>
""")

sop(2, "Payment types & ZiG", "shop,admin", "Cashiers · Supervisor on duty",
    "Take every type of payment correctly so the cash-up balances.", """
<ul><li><b>US$ cash</b> – check big notes; give change in US$ where possible.</li>
<li><b>EcoCash / mobile money</b> – only hand over the goods when the confirmation message has come through. Write the reference on the slip.</li>
<li><b>Swipe / card</b> – keep the card machine slip in the drawer.</li>
<li><b>Bank transfer</b> – only for invoices; the Manager confirms the money is in the bank before the goods leave.</li>
<li><b>ZiG</b> – use the <b>bank's ZiG rate of the day</b>. The manager checks the rate every morning before opening and writes it on the till board and on the cash-up. ZiG notes are counted separately at the cash-up.</li></ul>
<p>Never accept cheques, IOUs or “I'll pay tomorrow”.</p>
""")

# ======================================================================= 3 PRODUCTION
sop(3, "Production plan & model stock", "production,admin", "Day Supervisor · Night Supervisor",
    "Bake the right amounts every shift – not too little, not too much.", """
<ol>
<li>Before every shift the Supervisor makes the <b>production plan</b> in Pondo (<i>Production</i>) for the day or night shift.</li>
<li>Type what is still on the shelf and what has expired; Pondo suggests what to make from the <b>model stock</b>.</li>
<li>Add special and bulk orders for the next day.</li>
<li>Set the plan to <b>Final</b> and print the plan, the ingredient list and the recipe cards for the bakers.</li>
<li>At the end of the shift mark the plan <b>Done</b>.</li>
</ol>
<p>Too much waste of a product (“Over-production”)? Lower its model stock. Sold out early every day? Raise it. Only the Manager changes model stock.</p>
""")

sop(3, "Taking ingredients for production", "production,admin", "Team leaders · Supervisor on duty",
    "Only take what the plan needs, oldest first, and record it.", """
<ol>
<li>Every team (cakes &amp; confectionery, pies, savoury, burgers, night shift) gets its part of the printed <b>ingredient list</b> of the production plan.</li>
<li>The <b>team leader</b> takes the ingredients for their own team from the stock under the tables, the walk-in fridge and the walk-in deep freezer – other team members don't help themselves.</li>
<li>Always take the <b>oldest stock first</b> (first in, first out). Check the expiry date.</li>
<li>Tick every item on the list as you take it and <b>sign the list</b>. Anything not there or running low: tell the Supervisor at once.</li>
<li>Close opened bags properly and label them with the date opened. Put the rest back neatly, oldest in front, and close the walk-in doors properly.</li>
<li>The signed lists are handed to the Supervisor at the end of the shift and kept with the production plan.</li>
</ol>
""")

sop(3, "Baking to recipe & quality check", "production", "Bakers & confectioners · Supervisor on duty (quality check)",
    "Every product is made exactly to the Pondo recipe and looks and tastes the same every time.", """
<ol>
<li>Wash your hands and put on your uniform, apron and hair net before you start.</li>
<li>Use the <b>recipe card</b> from Pondo for every product. Weigh every ingredient on the scale – never guess.</li>
<li>Scale the dough to the <b>scaling weight</b> on the card.</li>
<li>Bake at the temperature and time on the card. Check the oven is at temperature before loading.</li>
<li>The <b>Supervisor on duty</b> checks every batch before it goes to the shop or is packed: size, weight, colour, bake, shape, filling and taste standard. Products that are not right are <b>not sold</b> – log them as waste (“Burnt / quality”).</li>
<li>Let products cool before packing, labelling or putting them on display.</li>
</ol>
<p>No eating or tasting of products or ingredients (see SOP “Staff food”).</p>
<p><b>Recipe cards are confidential:</b> no photos, no copies, and they never leave the bakery. The Supervisor collects them at the end of the shift (see SOP “Company recipes are confidential”).</p>
""")

sop(3, "Labelling & sell-by dates", "production,shop", "Packer / Orders clerk · Bakers · Counter staff",
    "Every packed product shows clearly when it was packed and until when it may be sold.", """
<ol>
<li>Every packed product gets a <b>PLU label</b> showing the product name, the price, the <b>packed date</b> and the <b>expiry (sell-by) date</b>.</li>
<li>Check the label before sticking it on: right product, right price, right dates. Wrong labels are thrown away, never stuck over.</li>
<li>Products with allergens (nuts, eggs, milk, wheat) carry the allergen on the label.</li>
<li>Never change, cover or remove an expiry date.</li>
<li>Unpacked products on the display: the counter staff know the packed date of every tray.</li>
</ol>
<h3>Leftovers at closing</h3>
<ul><li>Products still within their expiry date are kept and <b>sold first the next day</b> – they go to the front of the shelf.</li>
<li>Products past their expiry date are logged as waste – never re-labelled.</li></ul>
""")

sop(3, "Logging waste", "production,shop,admin", "Supervisor on duty",
    "Everything that leaves the bakery without being sold is written down – honestly.", """
<ol>
<li>Waste is logged at the end of <b>every shift</b> in Pondo (<i>Waste</i>) – one log per shift.</li>
<li>For every product: the quantity and the reason – <i>Expired, Damaged, Over-production, Burnt / quality, Customer return</i> or <i>Other</i>.</li>
<li>The waste is shown to the Supervisor before it is thrown away.</li>
<li>The Manager signs off the waste log.</li>
<li>Waste is <b>never</b> taken home or given away without the Manager's permission.</li>
</ol>
<p>The target is at most <b>5% of sales</b>.</p>
""")

sop(3, "Company recipes are confidential", "all", "All staff · Supervisor on duty · Manager",
    "Our recipes are the heart of Pondo Bakery. They belong to the company and are kept secret – always.", """
<p><b>This is one of the most important rules in this file.</b> Breaking it is serious misconduct and can lead to dismissal.</p>
<h3>What is confidential</h3>
<ul><li><b>All recipes</b> and everything about them: ingredients, quantities, scaling weights, methods, oven temperatures and times, fillings, icings and decorations.</li>
<li>Recipe cards, production plans and ingredient lists printed from Pondo, and the recipe pages in Pondo itself.</li>
<li>Costings, prices of ingredients and supplier details.</li>
<li>They are the <b>property of Pondo Bakery</b> – not of the person who bakes them, and not of the person who brought a recipe with them.</li></ul>
<h3>Never – no exceptions</h3>
<ul><li><b>Never take a photo or video</b> of a recipe card, an ingredient list, a production plan or a Pondo screen with a recipe.</li>
<li><b>Never copy a recipe</b> – not by hand, not in a notebook, not on a piece of paper, not in a phone note.</li>
<li><b>Never keep any recipe on your phone</b>, tablet or computer: no photos, notes, voice notes, WhatsApp messages, e-mails, cloud storage or social media.</li>
<li><b>Never take recipe cards or printed lists out of the bakery</b> – not home, not to the staff room, not in your bag or pocket.</li>
<li><b>Never share or tell</b> our recipes to anybody outside the company – family, friends, other bakeries, ex-staff or customers.</li>
<li><b>Never use our recipes</b> for your own business, for selling from home or for another employer – also <b>after you have left</b> Pondo Bakery.</li></ul>
<h3>Recipe cards in the bakery</h3>
<ol>
<li>Recipe cards and ingredient lists are printed from Pondo only for the shift, by the Supervisor.</li>
<li>They stay in the production area while you work.</li>
<li>At the end of the shift the Supervisor <b>collects and counts every card</b>. Old copies are torn up or shredded – never thrown away whole.</li>
<li>A missing recipe card is reported to the Manager the same day.</li>
<li>Only people with the right in Pondo can see recipes on the screen. Never show a recipe screen to somebody who doesn't have that right.</li>
</ol>
<h3>Phones in the bakery</h3>
<ul><li>Phones stay on silent in your pocket or bag – <b>never taken out in the bakery</b> or near recipe cards or a Pondo screen.</li>
<li>A phone taken out near recipes is reported to the Supervisor and the Manager.</li></ul>
<h3>Checks</h3>
<ul><li>Security checks bags for recipe cards and printed lists when staff leave.</li>
<li>The Manager may ask to see that no recipe is kept on a work phone or device.</li>
<li>If you see somebody photographing or copying a recipe, tell the Supervisor or the Manager straight away. It will be handled in confidence.</li></ul>
<h3>What happens if this rule is broken</h3>
<ul><li>It is <b>serious misconduct</b>, dealt with under the disciplinary code – usually a disciplinary hearing, which can end in <b>dismissal</b>.</li>
<li>The company may also take <b>legal action</b> for the damage caused, also after the person has left.</li>
<li>Every staff member signs that they have read and understood this SOP.</li></ul>
""")

# ======================================================================= 4 FOOD SAFETY
sop(4, "Uniform, personal hygiene & medical certificate", "all", "All staff · Supervisor on duty · Managers",
    "Keep our food safe and our team looking professional – every day, every shift.", """
<h3>Your uniform</h3>
<ul><li>Every staff member gets <b>two (2) sets</b> of uniform, signed for on the <b>Uniform issue &amp; return</b> form (Pondo Forms), which is kept in the staff file.</li>
<li>Items, depending on the job: pants, golf T-shirts, chef jacket, half-moon cap, chef's hat, safety shoes and a winter jacket – and a <b>name badge</b>.</li>
<li>The <b>name badge is compulsory</b> and is part of the uniform.</li>
<li>Wear the <b>full, clean uniform every day</b>. Working in your own clothing is <b>not allowed</b>.</li>
<li>No proper uniform: you are <b>sent home</b> and the day counts as an <b>unpaid leave day</b>.</li>
<li>Lost or stolen items are re-ordered and <b>paid for by the staff member</b>.</li>
<li>When you leave, the <b>full uniform</b> and name badge are returned <b>before any money is paid</b> to you. Missing items are deducted from that payment.</li></ul>
<h3>Colours per section – no swapping</h3>
<table><tr><th>Section / job</th><th>Shirt</th><th>Chef jacket</th></tr>
<tr><td>Supervisors, Manager, Assistant Manager, Owner</td><td>White</td><td>White (supervisors in the bakery)</td></tr>
<tr><td>Confectioners, pie chefs, night shift</td><td>Brown</td><td>Brown</td></tr>
<tr><td>Grillers and chefs</td><td>Maroon</td><td>Maroon</td></tr>
<tr><td>Counterhands (shop floor)</td><td>Orange</td><td>–</td></tr>
<tr><td>Cashiers</td><td>Teak green</td><td>–</td></tr>
<tr><td>Security</td><td>Brown</td><td>–</td></tr></table>
<p>Shirts are colour-coded per section and <b>may not be swapped</b>.</p>
<h3>Hygiene</h3>
<ul><li>A valid <b>medical certificate</b> (food handler's) before your first shift, renewed when it runs out. Pondo shows when it runs out.</li>
<li>All hair covered by the cap or hat. <b>Closed safety shoes</b> in the bakery.</li>
<li><b>No jewellery</b> (rings, watches, earrings, bracelets).</li>
<li>Nails <b>short and clean</b> – no nail polish or false nails.</li></ul>
<h3>When you are sick</h3>
<ul><li>Diarrhoea, vomiting, fever or an infected cut: tell the Supervisor <b>before</b> your shift. You may not handle food.</li>
<li>Cuts are covered with a blue plaster and a glove.</li></ul>
<h3>Never</h3>
<ul><li>No smoking, eating, chewing gum or spitting in the bakery, the walk-in fridge or freezer, or behind the counter.</li></ul>
""")

sop(4, "Hand washing", "all", "All staff · Day and Night Supervisor",
    "Clean hands stop germs getting into our food.", """
<h3>The Supervisor's duty</h3>
<p>At the start of every shift the Day or Night Supervisor makes sure <b>every hand basin</b> has soap, paper towels and a bin, and that the basins are clean and free – exactly as this SOP says. Anything missing is replaced straight away and written on the cleaning checklist.</p>
<h3>Wash your hands</h3>
<ul><li>When you start work and after every break.</li>
<li>After the toilet, eating, smoking, coughing or sneezing, touching your face, hair or phone.</li>
<li>After handling money, rubbish, raw eggs or meat, and cleaning chemicals.</li>
<li>Before handling food or putting on gloves.</li></ul>
<h3>How</h3>
<ol><li>Wet your hands with clean warm water.</li>
<li>Use soap and rub for <b>20 seconds</b>: palms, backs, between the fingers, thumbs, nails and wrists.</li>
<li>Rinse well.</li>
<li>Dry with a paper towel and use it to close the tap.</li></ol>
<p>Hand basins are for hands only – never for washing food or equipment.</p>
""")

sop(4, "Clean as you go & end-of-shift cleaning", "all", "All staff · Day and Night Supervisor",
    "A clean bakery and shop all day, every day – and every shift hands over a clean place to the next one.", """
<h3>The Supervisor's duty</h3>
<p>The Day and Night Supervisor are responsible for making sure everything is in place and done <b>exactly as this SOP says</b>: cleaning materials, chemicals, hand basins, checklists – and that the cleaning is really done.</p>
<h3>Clean as you go</h3>
<ul><li>Spills are cleaned <b>straight away</b>.</li>
<li>Wash and put away tools, bowls and trays as soon as you have finished with them.</li>
<li>Keep your work table clear – only what you need for the product you are making.</li>
<li>Flour bins, sugar bins and bags are closed after use.</li></ul>
<h3>After every shift (day and night)</h3>
<ol>
<li>Machines (mixers, dividers, slicers) switched off and unplugged, then cleaned.</li>
<li>Tables, shelves and scales washed and sanitised.</li>
<li>Ovens and proofers wiped down when cool.</li>
<li>Trays, tins and utensils washed, dried and stored.</li>
<li>Floors swept and mopped. Bins emptied, washed and new bags put in.</li>
<li>Shop: display, counters, glass, tills and floor cleaned. Toilets cleaned and stocked.</li>
<li>Every task is ticked and initialled on the <b>Shift cleaning checklist</b> (Pondo Forms). The Supervisor signs it.</li>
</ol>
<h3>Hand over a clean place</h3>
<ul><li>The <b>night shift leaves the bakery clean for the day shift</b>, and the <b>day shift leaves it clean for the night shift</b>.</li>
<li>The incoming Supervisor checks the bakery at the hand-over and signs the checklist. Anything not clean is written in the hand-over book and cleaned by the outgoing shift before they leave.</li></ul>
<h3>Saturday deep cleaning – 13:00 to 16:00</h3>
<ul><li>Every Saturday the whole bakery, the walk-in fridge and freezer and the shop are deep cleaned <b>from 13:00 to 16:00</b>, so nobody stays behind after closing.</li>
<li>Production stops in time for ovens, proofers, mixers, fridges, freezers, walls, drains and the stock areas under the tables to be cleaned.</li>
<li>The Supervisor fills in the <b>Saturday deep-cleaning checklist</b> (Pondo Forms): who did each task and that it was checked.</li>
<li>The shop stays closed until Monday – leave it spotless: no food left out, bins emptied and washed.</li></ul>
<h3>Cleaning chemicals</h3>
<ul><li>We use: <b>food-safe sanitiser</b>, <b>degreaser</b>, <b>dishwashing liquid</b>, <b>floor cleaner</b>, <b>oven cleaner</b>, <b>toilet cleaner</b> and <b>hand soap</b>.</li>
<li>Chemicals are bought <b>where they are cheapest</b> at the time; the Supervisor checks the stock every Saturday and writes what is running low on the deep-cleaning checklist.</li>
<li>Always use a chemical as the label says (how much water, how long to leave it). Never mix chemicals.</li>
<li>Chemicals are kept in their own place, away from food, in labelled containers – never in food containers.</li></ul>
<h3>The food safety file</h3>
<p>All filled-in cleaning checklists, temperature logs and pest control records are kept in the <b>food safety file</b> in the office, newest in front, for at least 12 months. The Manager checks the file every week.</p>
""")

sop(4, "Fridge & freezer temperatures", "production,shop,admin", "Day and Night Supervisor",
    "Keep cold food cold and know straight away if a fridge or freezer fails.", """
<ol>
<li>Check and write down every fridge, freezer and display temperature <b>twice a day</b>: when opening and when closing – on the <b>Fridge &amp; freezer temperature log</b> (Pondo Forms), one sheet per month.</li>
<li>Correct temperatures: <b>fridges 0 °C to 5 °C</b>, <b>freezers −18 °C or colder</b>.</li>
<li>Write the temperature and your initials. Out of range: write it in the action column.</li>
<li>Out of range? Check the door is closed and the fridge is not overloaded, and check again after 30 minutes.</li>
<li>Still out of range: move the food to another fridge or freezer, tell the Manager, and call the repair company.</li>
<li>Food that was too warm for longer than 2 hours is thrown away and logged as waste.</li>
<li>At month end the full sheet goes into the food safety file.</li>
</ol>
""")

sop(4, "Pest control", "all", "Manager · Day and Night Supervisor · All staff",
    "Keep rats, mice, cockroaches, flies and birds out of the bakery.", """
<ul><li>The <b>contracted pest control company</b> services the shop <b>every month</b>.</li>
<li>Every visit is written on the <b>Pest control record</b> (Pondo Forms): date, technician, areas treated, what was found, bait stations checked, next visit – and signed by the technician and the Supervisor. The company's own service report is stapled to it.</li>
<li>Any sign of pests (droppings, chewed bags, live or dead insects) is reported to the Supervisor the <b>same day</b> and written under <i>Pest sightings</i> on the same form, with the action taken.</li>
<li>The records are kept in the food safety file.</li>
<li>Food is stored off the floor, in closed containers.</li>
<li>Doors and windows close properly; fly screens are kept in good repair.</li>
<li>Rubbish is taken out after every shift and bins are kept closed.</li>
<li>Never move or touch the bait stations.</li></ul>
""")

sop(4, "Allergens", "production,shop", "Bakers · Packer / Orders clerk · Counter staff",
    "Customers with allergies must be able to trust what we tell them.", """
<h3>The allergens we use</h3>
<ul><li><b>Wheat flour (gluten)</b> – in almost everything we bake.</li>
<li><b>Milk</b> · <b>Eggs</b> · <b>Nuts</b> · <b>Sesame</b> · <b>Soya</b>.</li></ul>
<h3>Rules</h3>
<ul><li>The allergens of every product are on its recipe in Pondo and on its PLU label.</li>
<li>Nuts and sesame are stored in closed, labelled containers on a separate shelf; utensils and tables used for them are washed before other use.</li>
<li>Because we bake with all of these in one bakery, <b>we never promise</b> a customer that a product is free of any allergen.</li>
<li>A customer asks if something contains an allergen and you are not 100% sure: <b>say you don't know</b> and call the Supervisor. Never guess.</li></ul>
""")

# ======================================================================= 5 STOCK
sop(5, "Ordering from suppliers", "production,admin", "Supervisors (prepare) · Manager & Assistant Manager (place)",
    "Order the right stock in time, at the agreed price, and keep a record of every order.", """
<h3>Supervisors prepare the order</h3>
<ol>
<li>The Supervisor checks the stock: under the tables, in the walk-in fridge and in the walk-in deep freezer, and <b>Stock levels</b> in Pondo (items below the re-order level are marked low).</li>
<li>The Supervisor makes the order in Pondo as a <b>draft</b> (<i>Orders → + New order</i>, or <i>Order what's low from this supplier</i>): supplier, items, packs and delivery date.</li>
<li>The Supervisor gives it to a manager – printed, or tells the manager the order number.</li>
</ol>
<h3>Only managers place orders</h3>
<ol>
<li>Only the <b>Manager</b> and the <b>Assistant Manager</b> place orders with suppliers. Supervisors and other staff never order from a supplier themselves.</li>
<li>The manager checks the order (quantities, prices, delivery date), changes it if needed, and sends it from Pondo by <b>e-mail</b> or <b>WhatsApp</b>. Pondo records when it was sent, how and by whom.</li>
<li>Phone orders are typed in Pondo too and marked as sent.</li>
<li>Deliveries are booked for <b>Monday – Friday, 07:00 – 16:00</b> only.</li>
</ol>
""")

sop(5, "Receiving goods (GRV)", "production,admin,security", "Managers and/or Supervisors · Security",
    "We only pay for what really arrived, in good condition, at the right price.", """
<h3>Delivery times</h3>
<p>Suppliers deliver <b>Monday – Friday, 07:00 – 16:00</b> only. Deliveries outside these times, on Saturdays or at night are <b>not accepted</b> unless a manager has agreed beforehand.</p>
<h3>Steps</h3>
<ol>
<li>Security lets the supplier in at the back door and stays with the delivery.</li>
<li>A <b>manager or the Supervisor</b> receives it – nobody else signs for goods.</li>
<li><b>Count and check every item</b> against the order and the invoice: quantity, pack size, expiry date, damage, temperature of cold and frozen goods.</li>
<li>Wrong, damaged or expired goods are <b>refused</b> and written on the invoice; the driver signs.</li>
<li>Sign the supplier's invoice only for what was really received.</li>
<li>Type the GRV in Pondo the <b>same day</b> (<i>Receive this order</i>), with the invoice number, the invoice total and the packs that arrived.</li>
<li>Put the goods away straight away – frozen goods into the walk-in deep freezer first, then chilled goods into the walk-in fridge, then dry goods under the tables – <b>oldest stock to the front</b>.</li>
<li>Staple the printed GRV to the invoice for the office.</li>
</ol>
""")

sop(5, "Storing stock & first in, first out", "production,admin", "Day and Night Supervisor · Team leaders",
    "Stock is stored safely and the oldest stock is always used first.", """
<h3>Where stock is kept</h3>
<p>There is no separate store room:</p>
<ul><li><b>Dry stock</b> (flour, sugar, packaging …) is packed <b>under the bakery tables</b>.</li>
<li><b>Chilled stock</b> goes in the <b>walk-in fridge</b>, <b>frozen stock</b> in the <b>walk-in deep freezer</b>.</li></ul>
<h3>Rules</h3>
<ul><li>New stock goes <b>behind</b> the old stock (first in, first out).</li>
<li>Nothing stands directly on the floor – use shelves, crates or pallets under the tables, so the floor can be cleaned.</li>
<li>Bags and containers are closed and labelled; opened packs show the date opened.</li>
<li>Raw and ready-to-eat food are kept apart in the walk-in fridge: ready-to-eat on top, raw below.</li>
<li>Walk-in doors are kept <b>closed</b> – never propped open.</li>
<li>Chemicals are stored away from food, never under the bakery tables with ingredients.</li>
<li>Expired or damaged stock is taken out, logged and shown to the Manager.</li></ul>
""")

sop(5, "Daily shop floor rotation & removing expired stock", "shop,admin", "Counter staff · Supervisor on duty",
    "Customers only ever find fresh products, and nothing expired is ever sold.", """
<ol>
<li>Every morning before opening, and again in the afternoon, check <b>every product</b> on the shelves, display and fridges.</li>
<li>Move older products (still within the sell-by date) to the <b>front</b>; new products go behind.</li>
<li>Anything past its sell-by date, damaged or not looking right is <b>removed at once</b> and logged as waste.</li>
<li>Keep the display full and neat; empty spaces are filled or the tray is removed.</li>
<li>The Supervisor checks the rotation and signs the checklist.</li>
</ol>
""")

sop(5, "Weekly stock take", "production,admin", "Supervisor on duty · one baker · Manager",
    "Know the real stock and find losses early.", """
<ol>
<li>The stock take is done <b>every Saturday from 14:00 to 16:00</b> by the <b>Supervisor and one baker</b> – while the rest of the team does the deep clean.</li>
<li>In Pondo: <i>Stock → Stock take → Start stock take</i>, and print the <b>empty count sheets</b>. The sheets never show what the stock should be.</li>
<li>Count everything under the tables, in the walk-in fridge, in the walk-in deep freezer and on the shop floor, in the unit on the sheet (kg, litre, each).</li>
<li>One counts, the other writes. Both sign the sheet.</li>
<li>Type the counts in Pondo and open the <b>variance report</b>: expected against counted, short or over, and the value.</li>
<li><b>Recount</b> every item that is short or over, type the new count, and check the report again – until you are satisfied.</li>
<li>Every difference of <b>$100 or more</b> must have a written reason (e.g. bag torn, GRV typed wrong, product not logged as waste).</li>
<li><b>Only a manager</b> finalises the stock take. Stock levels then start from these counts. The printed variance report is kept in the stock file.</li>
</ol>
<p>Expected stock = last stock take + goods received (GRV) − everything sold on the till and logged as waste. So every delivery must be on a GRV and every waste on the waste log – otherwise the stock take shows false shortages.</p>
""")

sop(5, "Equipment care & monthly count", "production,admin", "Supervisor on duty · Manager",
    "Look after our equipment and know where every item is.", """
<ul><li>Use every machine only for what it is meant for, and only if you were trained on it.</li>
<li>Faults and breakages are reported to the Supervisor straight away and written in the hand-over book.</li>
<li>Every item has an asset number (EQ-…) that matches the equipment register in Pondo.</li>
<li>The equipment is counted on the <b>last Saturday of every month</b> in Pondo (<i>Equipment → Monthly count</i>) – print the count sheet, count, and type the numbers in. Missing items are reported to the Manager.</li></ul>
""")

# ======================================================================= 6 CUSTOMERS
sop(6, "Serving customers & the counter display", "shop", "Counter staff · Cashiers",
    "Every customer is welcomed, served quickly and leaves smiling.", """
<ol>
<li>Greet every customer within a few seconds, with a smile and eye contact.</li>
<li>Use tongs or gloves to handle products – never bare hands.</li>
<li>Tell customers about today's specials.</li>
<li>Pack products neatly in the right bag or box.</li>
<li>Thank the customer: “Thank you – see you tomorrow!”</li>
</ol>
<h3>The display</h3>
<ul><li>Full, neat and clean all day. Every product has the right price card.</li>
<li>Glass and counters are wiped regularly; crumbs are removed.</li></ul>
""")

sop(6, "Complaints, returns & refunds", "shop,admin", "Counter staff · Cashiers · Supervisor on duty · Managers",
    "Handle unhappy customers calmly and fairly – and protect our food safety.", """
<h3>Food that has left the shop</h3>
<p><b>No food items are exchanged or taken back once they have left the premises.</b> We can't know how the food was kept after it left the shop.</p>
<h3>At the counter</h3>
<ol>
<li>Listen to the customer without interrupting. Say sorry.</li>
<li>A problem noticed <b>before the customer leaves the shop</b> (wrong product, damaged, not right): replace it with the same product.</li>
<li><b>Refunds</b> are only given with a <b>reasonable reason</b> and the till slip:
  <ul><li>up to <b>US$5</b> – the <b>Supervisor</b> may approve it;</li>
  <li>more than <b>US$5</b> – only with a <b>manager's</b> approval.</li></ul></li>
<li>A replaced or refunded product is logged as waste with the reason <b>Customer return</b>.</li>
</ol>
<h3>The complaints register</h3>
<ul><li>Every complaint is written in the <b>complaints register</b> (Pondo Forms) kept in a file at the counter: date and time, customer and phone number, product, what was wrong, who took it, and the <b>action taken</b>.</li>
<li>The Supervisor checks the register <b>every day</b> and initials it. Complaints without an action are followed up the same day.</li>
<li>Serious complaints – somebody got sick, or found something in the food – go to the Manager <b>straight away</b>. Ask the customer to keep the product and the slip; we investigate, but it is still not an exchange.</li></ul>
""")

sop(6, "Special & bulk orders", "shop,production,admin", "Supervisor on duty · Managers · Packer / Orders clerk",
    "Take special orders correctly and have them ready on time.", """
<h3>Notice</h3>
<ul><li><b>Normal cake orders:</b> at least <b>24 hours</b> before collection.</li>
<li><b>Special orders</b> (special cakes, bulk and function orders): at least <b>48 hours</b>.</li></ul>
<h3>Taking the order</h3>
<ol>
<li>Only a <b>Supervisor or a manager</b> takes special orders – at the counter, by phone or on WhatsApp.</li>
<li>Write the order on the <b>customer order form</b> (Pondo Forms): name, phone, products, quantity, design or message, date and time of collection.</li>
<li>Make a <b>quotation</b> in Pondo and give it to the customer.</li>
<li><b>No deposit, no order.</b> Take a <b>50% deposit</b> before the order is accepted – phone and WhatsApp orders are only accepted once the deposit is paid (EcoCash or at the till). Tell the customer clearly that the deposit is <b>non-refundable</b> – it covers our costs if the order is not collected. The balance is paid on collection.</li>
<li>Add the order to the production plan of the right shift.</li>
</ol>
<h3>Changes</h3>
<ul><li>If the order has <b>not been made yet</b>, the customer may change the collection date. Whether it can be done is decided by the managers and supervisors.</li>
<li>Once the order is made, the date can't be changed and the deposit is not refunded.</li></ul>
<h3>Ready on time</h3>
<ul><li>Every order must be <b>ready 30 minutes before</b> the collection time – packed, labelled and checked against the order form by the Packer / Orders clerk.</li></ul>
""")

sop(6, "Deliveries with a driver", "shop,admin,security", "Supervisor on duty · Cashiers · Security",
    "Get orders to customers safely with an inDrive driver and bring the money for the goods back.", """
<h3>How it works</h3>
<ul><li>Deliveries are done by drivers booked on <b>inDrive</b>.</li>
<li>Deliveries are <b>cash only</b>: the customer pays the driver for the goods <b>plus</b> the delivery fee.</li>
<li>The driver <b>keeps the delivery fee</b> and brings the <b>money for the goods</b> back to the shop.</li></ul>
<h3>Steps</h3>
<ol>
<li>Book the driver on inDrive. Make the delivery in Pondo (<i>Deliveries → + New delivery</i>) with the driver's name, cell and car registration, and print the delivery note and invoice.</li>
<li>Security checks the driver, the car and the <b>number plate</b> against the inDrive app or the driver's Pondo ID card before the order leaves.</li>
<li>One copy of the delivery note goes with the driver, one stays at the till.</li>
<li>When the driver comes back, the cashier counts the money for the goods, rings the goods up on the till and checks the delivery off in Pondo with the till slip number.</li>
<li>Short? Write it in Pondo – the driver list shows drivers who brought back too little. Don't use them again without a manager's approval.</li>
</ol>
""")

# ======================================================================= 7 STAFF & HR
sop(7, "Clocking in & attendance", "all", "All staff · Supervisor on duty",
    "Everybody is at work on time, every time, and hours are recorded correctly.", """
<ul><li>Work the shifts on the <b>roster</b>. Changes only with the Supervisor's approval.</li>
<li>Clock in on the <b>fingerprint clocking machine</b> when you arrive and clock out when you leave – also for breaks if the Supervisor asks.</li>
<li><b>No clocking, no pay.</b> Time that is not on the clocking machine is not paid.</li>
<li>Never clock in or out for somebody else – it is fraud and is dealt with under the disciplinary code.</li>
<li>Be in full uniform and at your place <b>at the start time</b> on the roster.</li>
<li>Late or absent? Phone the Supervisor <b>before</b> your shift starts.</li>
<li>The machine not working: tell the Supervisor at once. The Supervisor writes the times in the hand-over book and signs them.</li>
<li>Night shift may only leave after the morning hand-over.</li></ul>
""")

sop(7, "Breaks, phones & conduct", "all", "All staff",
    "Respectful, professional behaviour at all times.", """
<ul><li>Breaks: <b>1 hour</b> per shift, taken at the time the Supervisor gives, so the counter and bakery are never left unattended.</li>
<li>Cell phones are allowed on <b>silent</b> but <b>never</b> used at the counter or in production. Calls and messages during breaks.</li>
<li>Never take a photo or video of recipes, recipe cards or Pondo screens (see SOP “Company recipes are confidential”).</li>
<li>Treat customers and colleagues with respect – no shouting, swearing or fighting.</li>
<li>No alcohol or drugs at work; nobody comes to work under the influence.</li>
<li>No visitors in the bakery or behind the counter.</li></ul>
""")

sop(7, "Staff food – no eating or tasting", "all", "All staff · Manager",
    "Products and ingredients are for sale, not for staff to eat.", """
<ul><li>Part of every salary is for food every day.</li>
<li><b>No eating or tasting</b> of products or ingredients at work – unless the Manager or a manager allows it.</li>
<li>Staff who want to buy products pay at the till like any customer and keep the slip.</li>
<li>Breaking this rule is serious misconduct and is dealt with under the disciplinary code.</li></ul>
""")

sop(7, "Leave & sick days", "all", "All staff · Manager",
    "Plan leave fairly and always know who is at work.", """
<ol>
<li>Apply for leave on the <b>leave application form</b> (Pondo Forms) at least <b>2 weeks</b> before.</li>
<li>Leave is only taken once the Manager has approved and signed it. It is recorded in Pondo.</li>
<li>Sick: phone the Supervisor <b>before your shift</b>.</li>
<li>Sick for more than <b>2 days</b>: bring a doctor's note when you come back.</li>
</ol>
""")

sop(7, "Discipline", "all", "Manager · Owner / Director",
    "Deal with misconduct fairly, the same for everybody, under the National Employment Code of Conduct (SI 15 of 2006).", """
<h3>Steps</h3>
<ol>
<li><b>Verbal warning</b> – for a first minor offence. Written down in the staff file.</li>
<li><b>Written warning</b> – for a repeat or more serious offence. Valid 6 months.</li>
<li><b>Final written warning</b> – valid 12 months.</li>
<li><b>Disciplinary hearing</b> – for serious misconduct (theft, fraud, violence, being drunk at work, gross negligence) or misconduct during a final warning. The staff member may be suspended while it is investigated.</li>
</ol>
<h3>Always</h3>
<ul><li>The staff member is told in writing what they are accused of and may answer and bring a representative.</li>
<li>Every step is recorded and kept in the staff file.</li>
<li>Only the Manager or the Owner / Director gives written warnings and holds hearings.</li></ul>
""")

sop(7, "New staff induction", "admin", "Manager · Supervisor on duty",
    "New staff start safely, know the rules and are set up correctly in Pondo.", """
<h3>Contracts</h3>
<ul><li>All staff are employed on a <b>month-to-month</b> basis.</li>
<li>A new staff member gets up to <b>three one-month contracts</b> (fixed term contract in Pondo Forms) before moving to month to month.</li></ul>
<h3>Before the first day</h3>
<ol>
<li>Contract signed, ID and medical certificate copied, staff member added in Pondo with a staff number.</li>
<li>Staff number registered on the fingerprint clocking machine.</li>
<li>Two sets of uniform and a name badge issued and signed for on the <b>Uniform issue &amp; return</b> form.</li>
</ol>
<h3>First day and week</h3>
<ol>
<li>Tour of the shop, toilets, fire exits, the <b>assembly point in front of the shop</b>, the first aid kit and the fire extinguishers.</li>
<li>The Supervisor goes through the SOPs for their job – always including <b>“Company recipes are confidential”</b>. The new staff member signs the SOP sign-off sheets.</li>
<li>Work next to an experienced colleague for the first week.</li>
</ol>
""")

sop(7, "Bag checks & security duties", "all", "Security · Supervisor on duty",
    "Protect the shop, the stock and the staff.", """
<ul><li>Staff bags are kept in the staff room, never in the bakery or behind the counter.</li>
<li>Security checks <b>every staff bag</b> when staff leave. Nobody is excused.</li>
<li>Products found without a till slip are reported to the Supervisor.</li>
<li>Recipe cards, ingredient lists or any copy of a recipe found in a bag are taken back and reported to the Manager the same day (see SOP “Company recipes are confidential”).</li>
<li>Security works the shifts the Manager sets. When Security is not on duty, the Supervisor on duty keeps the doors locked (see SOP “Night shift start &amp; hand-over”).</li>
<li>Security also checks the night shift's bags when they leave at 07:00.</li>
<li>Security controls the back door: only staff on duty, suppliers and contractors who are expected.</li>
<li>Security stays with suppliers and contractors while they are inside.</li></ul>
<h3>Keep security private</h3>
<ul><li>Never tell anybody outside the company about our security: keys, the safe, cash, who is on duty, when the building is closed or how doors are locked. Not to family, friends, ex-staff or on social media.</li>
<li>Anybody asking strange questions about these things is reported to the Manager.</li></ul>
""")

sop(7, "Confidential salaries & staff files", "all", "All staff · Manager · Owner / Director",
    "Keep everybody's pay and personal information private.", """
<h3>Salaries are confidential</h3>
<ul><li>Your salary, payslip, advances and deductions are <b>between you and the company</b>.</li>
<li>Staff may <b>not</b> discuss or compare salaries with fellow workers, show their payslip to others, or ask others what they earn.</li>
<li>Questions about your pay go only to the Manager, in private.</li>
<li>Breaking this rule is misconduct and is dealt with under the disciplinary code.</li></ul>
<h3>Staff files</h3>
<ul><li>Staff files (contracts, IDs, medical certificates, warnings, leave forms) are kept <b>locked in the office</b>.</li>
<li>Only the <b>managers</b>, the <b>Owner / Director</b> and the person who does <b>HR</b> may open them. Nobody else, for any reason.</li>
<li>In Pondo, staff records, papers and the payroll can only be seen by people with the <i>Staff &amp; payroll</i> right.</li>
<li>Files and payslips are never left on a desk, printer or screen where others can see them. Payslips are handed over in a sealed envelope.</li>
<li>A staff member may ask to see their <b>own</b> file, in the office, with a manager present.</li>
<li>The flash-drive backup also holds staff information – it is locked away.</li></ul>
""")

# ======================================================================= 8 HEALTH & SAFETY
sop(8, "Fire", "all", "Supervisor on duty · All staff · Manager",
    "Get everybody out safely if there is a fire, and keep the fire equipment ready.", """
<h3>If there is a fire</h3>
<ol>
<li>Shout <b>“FIRE!”</b> and tell the Supervisor.</li>
<li>Only if it is small and safe: use the right fire extinguisher or fire blanket. Never use water on an electrical or oil fire.</li>
<li>Switch off the power at the main switch if it is safe.</li>
<li>Get everybody out through the nearest exit to the <b>assembly point in front of the shop</b>. Don't stop for belongings.</li>
<li>The Supervisor counts everybody against the roster and phones the fire brigade.</li>
<li>Nobody goes back in until the fire brigade says it is safe.</li>
</ol>
<h3>Fire equipment</h3>
<ul><li>Fire exits are never blocked or locked during working hours.</li>
<li>Every fire extinguisher and fire blanket is <b>serviced every year</b> by the contracted company.</li>
<li>Each service is written on the <b>Fire extinguisher &amp; first aid kit record</b> (Pondo Forms) and signed off by a manager; the record is kept in the <b>health &amp; safety file</b>.</li></ul>
""")

sop(8, "Power cuts", "all", "Supervisor on duty",
    "Protect products, equipment and money when the power goes off. Our ovens are electric and there is no generator.", """
<ol>
<li>Stay calm. Switch off ovens, mixers and machines at the switch so they don't start by themselves when the power comes back.</li>
<li>Products in the oven: leave the door closed. Check them when the power is back – if not right, log as waste.</li>
<li>Dough in production: put it in the fridge to slow it down if possible.</li>
<li>Keep fridges and freezers <b>closed</b>. A closed freezer stays cold for several hours.</li>
<li>Tills: write sales by hand on a sales sheet if the tills are off, and ring them up when the power is back.</li>
<li>Write the time the power went off and came back in the hand-over book. Check fridge temperatures afterwards.</li>
<li>Switch machines on <b>one at a time</b> when the power is back.</li>
</ol>
""")

sop(8, "First aid & injuries", "all", "Day and Night Supervisor · All staff",
    "Help an injured person quickly and correctly – and always have a full first aid kit.", """
<h3>The first aid kit</h3>
<ul><li>The first aid kit is kept in a known place in the bakery.</li>
<li><b>Two supervisors</b> (the Day and the Night Supervisor) are responsible for it. They check it every month and after every use.</li>
<li>Missing or used items are written on the <b>Fire extinguisher &amp; first aid kit record</b> and the list is given to a manager, who orders them from the contracted company.</li></ul>
<h3>Injuries</h3>
<ul><li><b>Burns</b>: cool under running cold water for 20 minutes. No butter or oil.</li>
<li><b>Cuts</b>: press with a clean cloth, clean, cover with a blue plaster and a glove.</li>
<li>Serious injuries: call an ambulance; don't move the person unless they are in danger.</li>
<li>Every injury is written in the accident book and reported to the Manager the same day.</li></ul>
""")

sop(8, "Robbery", "all", "All staff",
    "Keep everybody alive and unhurt. Money and products can be replaced – people can't.", """
<h3>During</h3>
<ul><li><b>Do not resist.</b> Give what is asked, calmly.</li>
<li>Don't make sudden movements; keep your hands where the robbers can see them.</li>
<li>Look carefully: faces, clothes, height, voices, weapons, cars – but don't stare.</li></ul>
<h3>After</h3>
<ol>
<li>Lock the doors when they have gone. Make sure nobody is hurt.</li>
<li>Phone the police and the Manager.</li>
<li>Don't touch anything the robbers touched.</li>
<li>Each person writes down what they saw – on their own, before talking to others.</li>
<li>Close the shop until the police have finished.</li>
</ol>
""")

sop(8, "Using machines safely", "production", "Bakers & confectioners · Supervisor on duty",
    "Nobody gets hurt by an oven, mixer or slicer.", """
<ul><li>Only use a machine you were trained on and the Supervisor allowed you to use.</li>
<li>Never put your hands in a mixer, divider or slicer while it is running. Switch off and unplug before cleaning or clearing a blockage.</li>
<li>Guards stay on. Never bypass a safety switch.</li>
<li>Use oven gloves for hot trays. Tell people around you “Hot behind!”</li>
<li>Wet floors are mopped up straight away and marked with a sign.</li>
<li>Lift heavy bags (25 kg) with bent knees, or with two people.</li>
<li>Report faulty plugs, cables and machines at once and don't use them.</li></ul>
""")

sop(8, "When Pondo can't be used", "shop,production,admin", "Supervisor on duty · Manager",
    "Keep trading and keep every record when Pondo is down – no internet, a power cut, or a problem with the computer or server.", """
<h3>Be ready</h3>
<ul><li>A <b>“Pondo down” file</b> is kept at the counter with at least <b>10 printed copies</b> of each sheet from Pondo Forms (<i>When Pondo is down</i>): the <b>Cash-up sheet – Pondo down</b> and the <b>Day log – Pondo down</b>.</li>
<li>The Supervisor checks every Monday that the file is full.</li></ul>
<h3>When Pondo is down</h3>
<ol>
<li>Keep trading – the <b>tills work on their own</b>; only Pondo is down.</li>
<li>The Supervisor tells the Manager straight away. Write the time it went down on the day log.</li>
<li>Write <b>everything</b> that would normally be typed in Pondo on the paper sheets: cash-ups (one sheet per till), waste, goods received (staple the invoice), orders and deposits, deliveries.</li>
<li>Cash-ups are done as normal: count with the Supervisor, both sign the sheet, cash sealed with the sheet and handed to the manager for the safe.</li>
<li>Production carries on with the last printed production plan and recipe cards.</li>
</ol>
<h3>When Pondo works again</h3>
<ol>
<li>The Supervisor types everything from the sheets into Pondo <b>the same day</b> (or first thing the next day) – oldest first.</li>
<li>On each sheet write <b>“Typed into Pondo”</b>, the date and your initials.</li>
<li>File the sheets in the cash-up file. They are kept for at least 12 months.</li>
</ol>
<p>Down for longer than <b>2 hours</b>: the Manager informs the Owner / Director and the person who looks after the server.</p>
""")
