import pdfplumber

with pdfplumber.open('/home/ubuntu/upload/وليدالنهدي.pdf') as pdf:
    page = pdf.pages[0]
    print('page', page.width, page.height)
    regions = {
        'customer_block': (0, 170, page.width * 0.52, 340),
        'customer_name': (180, 175, page.width * 0.52, 245),
        'customer_address': (0, 235, page.width * 0.52, 330),
        'order_block': (page.width * 0.52, 95, page.width, 175),
    }
    for name, box in regions.items():
        crop = page.crop(box)
        print('\n---', name, box, '---')
        print(repr(crop.extract_text(x_tolerance=2, y_tolerance=3)))
