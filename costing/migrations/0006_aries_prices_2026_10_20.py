"""Aries price list (20 Oct 2026): rand prices / R16.50 per US$ x 1.25 import cost.

Updates only Aries ingredients whose price and pack size are still what they were when the list was checked,
and records every change in the price history and the change log."""
from decimal import Decimal

from django.db import migrations

RATE_NOTE = "Aries price list 20 Oct 2026 (R16.50/$ x 1.25)"
PLAN = [
[
"10% Softy 25kg",
"25.0000",
"49.8438",
"25.0000",
"48.3333"
],
[
"100 & 1000 2.5kg",
"2.5000",
"14.2448",
"2.5000",
"13.8131"
],
[
"15% Long Life 25kg",
"25.0000",
"53.4115",
"25.0000",
"51.7929"
],
[
"20% Sweety Original 25kg",
"25.0000",
"51.9531",
"25.0000",
"50.3788"
],
[
"6% Crispy Roll Mix 25kg",
"25.0000",
"42.6562",
"25.0000",
"41.3636"
],
[
"7% Sourdough Loaf 25kg",
"25.0000",
"118.4896",
"25.0000",
"114.8990"
],
[
"Almonds Flaked 3kg",
"3.0000",
"57.5438",
"3.0000",
"55.8000"
],
[
"Amagwinya Mix (Vetkoek) 12.5kg",
"12.5000",
"17.3047",
"12.5000",
"16.7803"
],
[
"Aniseed 3kg",
"3.0000",
"23.2562",
"3.0000",
"22.5515"
],
[
"Apricot Jam 25kg",
"25.0000",
"43.1771",
"25.0000",
"41.8687"
],
[
"Ascorbic Acid Crystal Powder OXY100 25kg",
"25.0000",
"124.8698",
"25.0000",
"121.0859"
],
[
"Bakers Mix - Special 12.5kg",
"12.5000",
"33.2031",
"12.5000",
"32.1970"
],
[
"Baking Powder 20kg",
"20.0000",
"42.3125",
"20.0000",
"41.0303"
],
[
"Banana Essence 1lt",
"1.0000",
"5.1917",
"1.0000",
"5.0343"
],
[
"Bar One Spread 5kg",
"5.0000",
"61.3594",
"5.0000",
"59.5000"
],
[
"Bicarb Of Soda 5kg",
"5.0000",
"5.6823",
"5.0000",
"5.5101"
],
[
"Black Cherry Pie Filling 3kg",
"3.0000",
"14.7844",
"3.0000",
"14.3364"
],
[
"Black Jack 2.5kg",
"2.5000",
"6.3750",
"2.5000",
"6.1818"
],
[
"Black Pitted Olives (A10)",
"3.0000",
"13.8438",
"3.0000",
"13.4242"
],
[
"Blueberry Essence 1lt",
"1.0000",
"26.2100",
"0.6000",
"3.1553"
],
[
"Blueberry Pie Filling 3kg",
"3.0000",
"7.8375",
"3.0000",
"7.6000"
],
[
"Bunspice Essence 1lt",
"1.0000",
"10.1062",
"1.0000",
"9.8000"
],
[
"Calcium Propionate 5kg",
"1.0000",
"4.5700",
"25.0000",
"100.1258"
],
[
"Caramel Spread 3kg",
"3.0000",
"26.7812",
"3.0000",
"25.9697"
],
[
"Caramel Vermicelli 5kg",
"5.0000",
"19.6875",
"5.0000",
"19.0909"
],
[
"Carrot Cake Mix 100% 12.5kg",
"12.5000",
"27.5130",
"12.5000",
"26.6793"
],
[
"Castor Sugar 25kg",
"25.0000",
"44.0104",
"25.0000",
"42.6768"
],
[
"Cheese Cake Premix 4kg",
"4.0000",
"33.2167",
"4.0000",
"32.2101"
],
[
"Cheese Pie Mix 5kg",
"5.0000",
"10.8229",
"5.0000",
"10.4949"
],
[
"Chicken Peri Peri Pie Mix 5kg",
"5.0000",
"13.7865",
"5.0000",
"13.3687"
],
[
"Chicken Pie Mix 5kg",
"5.0000",
"14.3698",
"5.0000",
"13.9343"
],
[
"Chocolate Block Dark 5kg",
"5.0000",
"39.5312",
"5.0000",
"38.3333"
],
[
"Chocolate Disk - White 12kg",
"12.0000",
"87.7500",
"12.0000",
"85.0909"
],
[
"Chocolate Nibs/Chips 15kg",
"15.0000",
"100.3125",
"15.0000",
"97.2727"
],
[
"Chocolate Vermicelli Dual 5kg",
"5.0000",
"21.6667",
"5.0000",
"21.0101"
],
[
"Cinnamon - Fine 25kg",
"25.0000",
"117.1875",
"25.0000",
"113.6364"
],
[
"Citric Acid 5kg",
"1.0000",
"22.0000",
"25.0000",
"43.6864"
],
[
"Cocoa Powder 25kg",
"25.0000",
"195.3125",
"25.0000",
"189.3939"
],
[
"Cocomix 12.5kg",
"12.5000",
"57.3438",
"12.5000",
"55.6061"
],
[
"Condensed Milk 25kg",
"25.0000",
"159.8698",
"25.0000",
"155.0253"
],
[
"Corn Flour 25kg",
"25.0000",
"26.8229",
"25.0000",
"26.0101"
],
[
"Cornish Pie Mix 5kg",
"5.0000",
"11.7031",
"5.0000",
"11.3485"
],
[
"Croissant Pastrex 25kg",
"25.0000",
"80.6510",
"25.0000",
"78.2071"
],
[
"Dates 10kg",
"10.0000",
"33.3333",
"10.0000",
"32.3232"
],
[
"Desiccated Coconut 15kg",
"15.0000",
"60.5938",
"15.0000",
"58.7576"
],
[
"Driekoppies Mix 25kg",
"25.0000",
"45.1302",
"25.0000",
"43.7626"
],
[
"Egg Yellow Colour Powder 1kg",
"1.0000",
"9.8552",
"1.0000",
"9.5566"
],
[
"Flan Gel Apricot 6lt",
"6.0000",
"31.5375",
"6.0000",
"30.5818"
],
[
"Garlic Powder 25kg",
"25.0000",
"73.8281",
"25.0000",
"71.5909"
],
[
"Gelatine 25kg (Halaal)",
"25.0000",
"651.0417",
"25.0000",
"631.3131"
],
[
"Ginger -Fine 25kg",
"25.0000",
"195.3125",
"25.0000",
"189.3939"
],
[
"Glucose 5kg",
"5.0000",
"7.6562",
"5.0000",
"7.4242"
],
[
"Gluten 25kg",
"25.0000",
"76.1719",
"25.0000",
"73.8636"
],
[
"Glycerine 5lt",
"5.0000",
"20.4323",
"5.0000",
"19.8131"
],
[
"Golden Syrup 25kg",
"25.0000",
"41.6667",
"25.0000",
"40.4040"
],
[
"Granadilla Pie Filling 3kg",
"3.0000",
"5.2969",
"3.0000",
"5.1364"
],
[
"Green Chellies 6kg",
"6.0000",
"31.7500",
"6.0000",
"30.7879"
],
[
"Green Cherries Whole 5kg",
"5.0000",
"78.1250",
"5.0000",
"75.7576"
],
[
"Herbs Mixed 15kg",
"15.0000",
"85.9375",
"15.0000",
"83.3333"
],
[
"Icing Sugar 25kg",
"25.0000",
"44.0104",
"25.0000",
"42.6768"
],
[
"Jelly Green 1 x 1kg",
"1.0000",
"6.2292",
"1.0000",
"6.0404"
],
[
"Jelly Strawberry 1kg",
"1.0000",
"6.2292",
"1.0000",
"6.0404"
],
[
"Lemington Chocolate 5kg",
"5.0000",
"17.4219",
"5.0000",
"16.8939"
],
[
"Lemington Strawberry 5kg",
"5.0000",
"13.0417",
"5.0000",
"12.6465"
],
[
"Lemon Essence 1lt",
"1.0000",
"5.1396",
"1.0000",
"4.9838"
],
[
"Lemon Juice 5 Ltr",
"5.0000",
"7.9479",
"5.0000",
"7.7071"
],
[
"Linseed 5kg",
"1.0000",
"4.5000",
"3.0000",
"8.6485"
],
[
"Mallowhip 6.5kg",
"6.5000",
"20.7120",
"6.5000",
"20.0843"
],
[
"Marsipan 12.5kg",
"12.5000",
"45.2604",
"12.5000",
"43.8889"
],
[
"Mix Seed 3kg",
"3.0000",
"12.1406",
"3.0000",
"11.7727"
],
[
"Mix Spice 3kg",
"3.0000",
"19.6281",
"3.0000",
"19.0333"
],
[
"Mixed Peel 15kg",
"1.0000",
"6.0000",
"15.0000",
"94.6970"
],
[
"Mousse Chocolate 4kg",
"4.0000",
"32.0333",
"4.0000",
"31.0626"
],
[
"Muffin Mix Bran 12.5kg",
"12.5000",
"24.8177",
"12.5000",
"24.0657"
],
[
"Oats Rolled 25kg",
"25.0000",
"56.7708",
"25.0000",
"55.0505"
],
[
"Orange Paste/Essence 1lt",
"1.0000",
"6.2969",
"1.0000",
"6.1061"
],
[
"PanGlide 4.8kg (Yellow)",
"4.8000",
"12.8950",
"4.8000",
"12.5042"
],
[
"Panini/Ciabatta Mix 50% 12.5kg",
"12.5000",
"21.1849",
"12.5000",
"20.5429"
],
[
"Parsley 5kg",
"5.0000",
"24.2292",
"5.0000",
"23.4949"
],
[
"Pecan Nuts 5kg (Halves)",
"5.0000",
"97.9167",
"5.0000",
"94.9495"
],
[
"Pepper Steak Pie Mix 5kg",
"5.0000",
"17.8646",
"5.0000",
"17.3232"
],
[
"Peppermint Essence 1lt",
"1.0000",
"5.5688",
"1.0000",
"5.4000"
],
[
"Pie Mix Beef Sausage Roll 5kg",
"1.0000",
"2.6000",
"5.0000",
"25.3833"
],
[
"Pie Mix Steak 5kg",
"5.0000",
"13.5104",
"5.0000",
"13.1010"
],
[
"Pie Mix Steak And Kidney 5kg",
"5.0000",
"12.0677",
"5.0000",
"11.7020"
],
[
"Pillar Box Green 1kg",
"1.0000",
"5.4760",
"1.0000",
"5.3101"
],
[
"Pillar Box Red 1kg",
"1.0000",
"3.7833",
"1.0000",
"3.6687"
],
[
"Pineapple Jelly 1kg",
"1.0000",
"6.2300",
"1.0000",
"6.1371"
],
[
"Pink Colouring 1kg",
"1.0000",
"4.1146",
"1.0000",
"3.9899"
],
[
"Plastic Icing 12.5kg",
"12.5000",
"31.7448",
"12.5000",
"30.7828"
],
[
"Poppy Seeds 5kg",
"5.0000",
"37.4531",
"5.0000",
"36.3182"
],
[
"Puff Pastry Fat 25kg Pastry King 16",
"25.0000",
"62.4740",
"25.0000",
"60.5808"
],
[
"Rainbow Vermicelli 5kg",
"5.0000",
"20.9375",
"5.0000",
"20.3030"
],
[
"Red Chellies 6kg",
"6.0000",
"30.4375",
"6.0000",
"29.5152"
],
[
"Red Cherries Whole 5kg",
"5.0000",
"72.3958",
"5.0000",
"70.2020"
],
[
"Red Velvet Paste 500ml",
"0.5000",
"13.5188",
"0.5000",
"13.1091"
],
[
"Release 30 25lt",
"25.0000",
"1.5000",
"25.0000",
"39.2674"
],
[
"Royal Cream Cheese Icing 5kg",
"5.0000",
"28.7083",
"5.0000",
"27.8384"
],
[
"Sesame Seeds 25kg",
"25.0000",
"93.7500",
"25.0000",
"90.9091"
],
[
"Silicone Paper Ream 450x750 -500 Sheets - 7.4kg",
"500.0000",
"78.7098",
"500.0000",
"76.3246"
],
[
"Sky Box Blue 1kg",
"1.0000",
"3.3531",
"1.0000",
"3.2515"
],
[
"Snow White 1kg",
"1.0000",
"16.3010",
"1.0000",
"15.8071"
],
[
"Special Instant Custard 20kg",
"20.0000",
"112.8958",
"20.0000",
"109.4747"
],
[
"SSL Platinum 20kg",
"20.0000",
"74.6875",
"20.0000",
"72.4242"
],
[
"Strawberry Essence 1lt",
"1.0000",
"4.6323",
"1.0000",
"4.4919"
],
[
"Strawberry Pie Filling 3kg (Bucket)",
"3.0000",
"6.4906",
"3.0000",
"6.2939"
],
[
"Strawberry Topping 5kg (Bucket)",
"5.0000",
"8.0156",
"5.0000",
"7.7727"
],
[
"Sugar Brown 25kg",
"25.0000",
"38.8021",
"25.0000",
"37.6263"
],
[
"Sugar White 25kg",
"25.0000",
"41.1458",
"25.0000",
"39.8990"
],
[
"Sunflower Oil 20 Litres - (19.48kg)",
"19.4800",
"73.0703",
"19.4800",
"70.8560"
],
[
"Sunflower Seeds 3kg",
"3.0000",
"9.2625",
"3.0000",
"8.9818"
],
[
"Tiramisu 4kg",
"4.0000",
"30.7542",
"4.0000",
"29.8222"
],
[
"True Soft 0.1% 25kg",
"25.0000",
"168.4896",
"25.0000",
"163.3838"
],
[
"Vanilla Essence Concentrate 10 Litre",
"5.0000",
"22.2865",
"5.0000",
"21.6111"
],
[
"Vanilla Powder 25kg (Cheap)",
"25.0000",
"356.7708",
"25.0000",
"345.9596"
],
[
"Vinegar 5 Litre",
"5.0000",
"5.3854",
"5.0000",
"5.2222"
],
[
"White Margarine 25kg",
"25.0000",
"55.3646",
"25.0000",
"53.6869"
],
[
"Xmas Mince 1 x 10kg",
"10.0000",
"34.0312",
"10.0000",
"33.0000"
],
[
"Yellow Margarine 25kg",
"25.0000",
"55.3646",
"25.0000",
"53.6869"
]
]


def apply(apps, schema_editor):
    Ingredient = apps.get_model("costing", "Ingredient")
    Change = apps.get_model("costing", "IngredientPriceChange")
    Log = apps.get_model("core", "ChangeLog")
    User = apps.get_model("auth", "User")
    boss = User.objects.filter(is_superuser=True).order_by("id").first()
    q = Decimal("0.0001")
    for name, old_s, old_p, new_s, new_p in PLAN:
        i = Ingredient.objects.filter(name=name, supplier__name="Aries").first()
        if not i or i.pack_price is None:
            continue
        if Decimal(i.pack_price).quantize(q) != Decimal(old_p) or Decimal(i.pack_size).quantize(q) != Decimal(old_s):
            continue  # changed by hand since – leave it
        i.pack_price, i.pack_size = Decimal(new_p), Decimal(new_s)
        i.save(update_fields=["pack_price", "pack_size"])
        Change.objects.create(ingredient=i, user=boss, old_price=Decimal(old_p), new_price=Decimal(new_p),
                              old_pack_size=Decimal(old_s), new_pack_size=Decimal(new_s))
        d = f"{RATE_NOTE}: price {old_p} → {new_p}" + (f", pack {old_s} → {new_s}" if old_s != new_s else "")
        Log.objects.create(user=boss, area="Ingredients", item=i.name, action="changed", details=d)


class Migration(migrations.Migration):
    dependencies = [("costing", "0005_longer_bake_notes"), ("core", "0021_sop_recipes")]
    operations = [migrations.RunPython(apply, migrations.RunPython.noop)]
