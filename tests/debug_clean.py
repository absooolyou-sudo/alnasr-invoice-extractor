from app import clean_value
for x in ['العزيزية', 'شارع لبيد بن ربيعة']:
    print(repr(x), repr(clean_value(x)))
