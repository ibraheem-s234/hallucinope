"""Places that are not countries: provinces, states, regions and large cities.

Population data covers countries and the World only. When a number is
about one of these places ("Quebec had 9 million people", "3 million live
in Toronto"), it must not be checked against the country's population;
real ChatGPT text produced exactly that false alarm. Such numbers go to
"not checked" instead.

Matching is case-sensitive (proper nouns only). Names that are also
countries (Georgia, Singapore, Hong Kong, Luxembourg...) are deliberately
absent: as countries they CAN be checked.
"""

from __future__ import annotations

import re

CANADA = ["Ontario", "Quebec", "British Columbia", "Alberta", "Manitoba", "Saskatchewan",
          "Nova Scotia", "New Brunswick", "Newfoundland and Labrador", "Newfoundland",
          "Prince Edward Island", "Yukon", "Northwest Territories", "Nunavut"]
US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming"]   # Georgia omitted: it is also a country
OTHER_REGIONS = ["England", "Scotland", "Wales", "Northern Ireland", "Catalonia", "Bavaria",
                 "Siberia", "Tasmania", "Queensland", "New South Wales", "Punjab",
                 "Uttar Pradesh", "Maharashtra", "Sichuan", "Guangdong", "Kerala"]
CITIES = [
    "Toronto", "Montreal", "Montréal", "Vancouver", "Calgary", "Edmonton", "Ottawa",
    "Winnipeg", "Quebec City", "Hamilton", "Kingston", "Halifax", "Victoria", "Regina",
    "Saskatoon", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia",
    "San Francisco", "Boston", "Miami", "Seattle", "London", "Paris", "Berlin", "Madrid",
    "Barcelona", "Rome", "Milan", "Moscow", "Istanbul", "Tokyo", "Osaka", "Seoul",
    "Beijing", "Shanghai", "Shenzhen", "Guangzhou", "Delhi", "New Delhi", "Mumbai",
    "Kolkata", "Bangalore", "Bengaluru", "Chennai", "Karachi", "Lahore", "Dhaka",
    "Jakarta", "Manila", "Bangkok", "Cairo", "Lagos", "Kinshasa", "Johannesburg",
    "Nairobi", "São Paulo", "Sao Paulo", "Rio de Janeiro", "Buenos Aires", "Lima",
    "Bogotá", "Bogota", "Mexico City", "Sydney", "Melbourne", "Tehran", "Baghdad",
    "Riyadh", "Dubai", "Ho Chi Minh City", "Hanoi", "Kyiv", "Warsaw", "Amsterdam",
    "Brussels", "Vienna", "Athens", "Lisbon", "Dublin", "Stockholm", "Prague", "Budapest"]

PLACES = CANADA + US_STATES + OTHER_REGIONS + CITIES
# Longest first, so "Quebec City" wins over "Quebec" and "New York" stays whole.
_PLACE_RE = re.compile(
    r"\b(" + "|".join(re.escape(p) for p in sorted(PLACES, key=len, reverse=True)) + r")\b")


def place_mentions(text: str) -> list[tuple[int, int, str]]:
    """(start, end, name) for every non-country place named in the text."""
    return [(m.start(), m.end(), m.group()) for m in _PLACE_RE.finditer(text)]
