"""Google Business Profile competition via Google's official Places API (New). Needs GOOGLE_PLACES_API_KEY."""
import os
from collections import Counter
from urllib.parse import quote, urlparse

import requests

URL = "https://places.googleapis.com/v1/places:searchText"
FIELDS = ",".join("places." + f for f in ("id", "displayName", "rating", "userRatingCount", "primaryTypeDisplayName",
                                          "websiteUri", "formattedAddress", "googleMapsUri", "businessStatus"))
CHECKLIST = [
    "Primary category and extra categories (are rivals using more specific ones?)",
    "Number of reviews, average rating, and how recent the latest reviews are",
    "Whether the owner replies to reviews",
    "Services or products listed, with descriptions",
    "Business description: is it clear and complete?",
    "Number and quality of photos, and how recently they were added",
    "How often they post updates or offers",
    "Opening hours, booking or appointment link, and website link",
]


def enabled():
    return bool(os.environ.get("GOOGLE_PLACES_API_KEY"))


class GbpError(Exception):
    pass


def manual_links(keywords):
    return [{"keyword": k, "url": "https://www.google.com/maps/search/" + quote(k)} for k in keywords]


def search(keyword, n=10):
    key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not key:
        raise GbpError("Google Places is not switched on. Add GOOGLE_PLACES_API_KEY in your server settings.")
    try:
        r = requests.post(URL, json={"textQuery": keyword, "pageSize": n, "languageCode": "en"}, timeout=20,
                          headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": FIELDS, "Content-Type": "application/json"})
    except requests.RequestException:
        raise GbpError("Could not reach Google. Try again.")
    if r.status_code in (400, 403):
        raise GbpError("Google rejected the request. Check the key is valid and that 'Places API (New)' is enabled for it.")
    if r.status_code == 429:
        raise GbpError("Google is rate limiting this key. Try again shortly.")
    if r.status_code != 200:
        raise GbpError(f"Google returned an error ({r.status_code}).")
    out = []
    for p in r.json().get("places", []):
        out.append({"name": (p.get("displayName") or {}).get("text", ""), "rating": p.get("rating"),
                    "reviews": p.get("userRatingCount") or 0,
                    "category": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
                    "website": p.get("websiteUri", ""), "address": p.get("formattedAddress", ""),
                    "maps_url": p.get("googleMapsUri", ""), "status": p.get("businessStatus", "")})
    return out


def _is_you(p, site_domain, name_tokens):
    host = (urlparse(p["website"]).hostname or "").lower().removeprefix("www.")
    if site_domain and host and (host == site_domain or host.endswith("." + site_domain)):
        return True
    return bool(name_tokens) and name_tokens <= set(p["name"].lower().split())


def analyze(keywords, site_domain, business_name):
    tokens = set(business_name.lower().split()) if business_name else set()
    results = []
    for kw in keywords[:5]:
        places = search(kw)
        for p in places:
            p["is_you"] = _is_you(p, site_domain, tokens)
        you = next((i for i, p in enumerate(places) if p["is_you"]), None)
        rivals = [p for p in places if not p["is_you"]][:3]
        notes = []
        if you is None:
            notes.append(f"Your business did not appear in the top {len(places)} results for this search.")
        else:
            notes.append(f"Your business is number {you + 1} of {len(places)} for this search.")
        if rivals:
            reviews = round(sum(p["reviews"] for p in rivals) / len(rivals))
            ratings = [p["rating"] for p in rivals if p["rating"]]
            avg = round(sum(ratings) / len(ratings), 1) if ratings else None
            notes.append(f"The top rivals average {reviews} reviews" + (f" and a {avg} rating." if avg else "."))
            if you is not None:
                mine = places[you]
                if mine["reviews"] < reviews:
                    notes.append(f"You have {mine['reviews']} reviews, {reviews - mine['reviews']} fewer than that average. More genuine reviews is the clearest gap to close.")
        cats = Counter(p["category"] for p in places[:5] if p["category"])
        if cats:
            notes.append("Most common main category among the top results: " + cats.most_common(1)[0][0] + ".")
        results.append({"keyword": kw, "places": places, "notes": notes})
    return {"results": results,
            "caveat": "Results come from Google's Places search. They are close to, but not identical to, what a customer sees in Maps, which depends on location and personalization."}
