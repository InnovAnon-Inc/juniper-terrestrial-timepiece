#! /usr/bin/env python

import datetime

def to_kaktovik(n: int) -> str:
    """Converts a base-10 integer into Kaktovik numerals (base-20)."""
    if n == 0:
        return chr(0x1D2C0)
    
    chars = []
    while n > 0:
        chars.append(chr(0x1D2C0 + (n % 20)))
        n //= 20
    
    # Reverse to put the most significant base-20 digit first
    return ''.join(reversed(chars))

def get_arcane_date(dt: datetime.date = None) -> str:
    """
    Converts a date into an arcane string format: 
    [day] [kaktovik day] [month] [kaktovik year] [zodiac animal] [wuxing element]
    """
    if dt is None:
        dt = datetime.datetime.now()

    # 1. Day of the week (Planetary/Alchemical)
    # Python weekday(): 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun
    planetary_days = ['☽', '♂', '☿', '♃', '♀', '♄', '☉']
    day_sym = planetary_days[dt.weekday()]

    # 2. Day of the month (Kaktovik)
    day_num = to_kaktovik(dt.day)

    # 3. Month of the year (Astrology)
    # 1-indexed (Jan=Aries, Dec=Pisces)
    astro_months = ['', '♈', '♉', '♊', '♋', '♌', '♍', '♎', '♏', '♐', '♑', '♒', '♓']
    month_sym = astro_months[dt.month]

    # 4. Year (Kaktovik)
    year_num = to_kaktovik(dt.year)

    # 5. Chinese Zodiac Animal (12-year cycle)
    # 0 = Monkey, 4 = Rat, 10 = Horse, etc.
    zodiac_animals = ['🐒', '🐓', '🐕', '🐖', '🐀', '🐂', '🐅', '🐇', '🐉', '🐍', '🐎', '🐐']
    animal_sym = zodiac_animals[dt.year % 12]

    # 6. Wu Xing Element (10-year cycle, changes every 2 years)
    # (year % 10) // 2 maps to: 0=Metal, 1=Water, 2=Wood, 3=Fire, 4=Earth
    wuxing_elements = ['⚙️', '💧', '🌿', '🔥', '🌍']
    element_sym = wuxing_elements[(dt.year % 10) // 2]

    return f"{day_sym} {day_num} {month_sym} {year_num} {animal_sym} {element_sym}"

# --- Example Usage ---
if __name__ == "__main__":
    # Test 1: Current Date (Default behavior)
    current_arcane = get_arcane_date()
    print(f"Today's arcane date: {current_arcane}")
    
    # Test 2: Specific Date (e.g., September 10, 2026 - A Thursday)
    # Thursday (♃) | 10 (𝋊) | September (♐) | 2026 (𝋅𝋁𝋆) | Horse (🐎) | Fire (🔥)
    test_date = datetime.datetime(2026, 9, 10)
    print(f"Custom arcane date:  {get_arcane_date(test_date)}")
