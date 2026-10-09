"""Curated, region-based directories and legitimate link routes. Static data: no keys, no cost."""

GLOBAL = [
    ("Google Business Profile", "https://business.google.com", "general", "The most important listing for local searches."),
    ("Bing Places", "https://www.bingplaces.com", "general", "Feeds Bing and other services."),
    ("Apple Business Connect", "https://businessconnect.apple.com", "general", "Shows your business in Apple Maps."),
    ("Facebook Page", "https://www.facebook.com/business", "general", "A page people can find, follow and review."),
    ("LinkedIn Company Page", "https://www.linkedin.com/company/setup/new/", "general", "Useful for B2B and trust."),
    ("Foursquare", "https://foursquare.com", "general", "Data from it feeds several other apps."),
]
REGIONAL = {
    "India": [
        ("Justdial", "https://www.justdial.com", "general", "Very widely used local directory in India."),
        ("Sulekha", "https://www.sulekha.com", "general", "Local services listings."),
        ("IndiaMART", "https://www.indiamart.com", "b2b", "For suppliers and manufacturers selling to businesses."),
        ("TradeIndia", "https://www.tradeindia.com", "b2b", "B2B marketplace."),
        ("Practo", "https://www.practo.com", "health", "Doctors and clinics."),
        ("Lybrate", "https://www.lybrate.com", "health", "Doctors and clinics."),
        ("WedMeGood", "https://www.wedmegood.com", "wedding", "Wedding vendors, including caterers."),
        ("WeddingWire India", "https://www.weddingwire.in", "wedding", "Wedding vendors."),
        ("Urban Company", "https://www.urbancompany.com", "home", "Apply as a service partner."),
    ],
    "USA": [
        ("Yelp", "https://biz.yelp.com", "general", "Reviews and discovery."),
        ("Better Business Bureau", "https://www.bbb.org", "general", "Trust profile."),
        ("Nextdoor", "https://business.nextdoor.com", "general", "Neighbourhood recommendations."),
        ("Manta", "https://www.manta.com", "general", "Small business directory."),
        ("YellowPages", "https://www.yellowpages.com", "general", "Classic directory."),
        ("Healthgrades", "https://www.healthgrades.com", "health", "Provider profiles."),
        ("Zocdoc", "https://www.zocdoc.com", "health", "Appointment booking."),
        ("The Knot", "https://www.theknot.com", "wedding", "Wedding vendors."),
        ("WeddingWire", "https://www.weddingwire.com", "wedding", "Wedding vendors."),
        ("Angi", "https://www.angi.com", "home", "Home services."),
        ("Thumbtack", "https://www.thumbtack.com", "home", "Home and local services."),
        ("ThomasNet", "https://www.thomasnet.com", "b2b", "Industrial suppliers."),
    ],
    "UK": [
        ("Yell", "https://www.yell.com", "general", "Large UK directory."),
        ("Yelp UK", "https://biz.yelp.co.uk", "general", "Reviews and discovery."),
        ("Thomson Local", "https://www.thomsonlocal.com", "general", "Local directory."),
        ("FreeIndex", "https://www.freeindex.co.uk", "general", "Free business directory."),
        ("Checkatrade", "https://www.checkatrade.com", "home", "Vetted tradespeople."),
        ("TrustATrader", "https://www.trustatrader.com", "home", "Vetted tradespeople."),
        ("Bark", "https://www.bark.com", "home", "Service requests from customers."),
        ("Hitched", "https://www.hitched.co.uk", "wedding", "Wedding vendors."),
        ("Trustpilot", "https://business.trustpilot.com", "general", "Customer reviews."),
    ],
    "Canada": [
        ("Yelp Canada", "https://biz.yelp.ca", "general", "Reviews and discovery."),
        ("Yellow Pages Canada", "https://www.yellowpages.ca", "general", "Classic directory."),
        ("Better Business Bureau", "https://www.bbb.org", "general", "Trust profile."),
        ("HomeStars", "https://homestars.com", "home", "Home services reviews."),
        ("RateMDs", "https://www.ratemds.com", "health", "Provider reviews."),
    ],
    "Australia": [
        ("Yellow Pages Australia", "https://www.yellowpages.com.au", "general", "Classic directory."),
        ("True Local", "https://www.truelocal.com.au", "general", "Local directory."),
        ("Localsearch", "https://www.localsearch.com.au", "general", "Local directory."),
        ("Yelp Australia", "https://biz.yelp.com.au", "general", "Reviews and discovery."),
        ("hipages", "https://www.hipages.com.au", "home", "Tradies and home services."),
        ("Oneflare", "https://www.oneflare.com.au", "home", "Service requests."),
        ("Easy Weddings", "https://www.easyweddings.com.au", "wedding", "Wedding vendors."),
    ],
    "UAE": [
        ("Yellow Pages UAE", "https://www.yellowpages.ae", "general", "Local directory."),
        ("Dubizzle", "https://www.dubizzle.com", "general", "Classifieds including services."),
    ],
}
INDUSTRIES = {"general": "Any business", "health": "Healthcare", "wedding": "Weddings and events",
              "home": "Home services", "b2b": "B2B and industrial"}

STRATEGIES = [
    ("Business directories and citations", "Days", "Low to medium", "Easy",
     "List your business with identical name, address and phone on the directories above. Little link power, but good for local trust and being found."),
    ("Unlinked brand mentions", "1 to 2 weeks", "High", "Easy",
     'Search Google for your business name in quotes, minus your own site. Where a page mentions you without a link, ask the owner to add one. They already like you.'),
    ("Partners, suppliers and clients", "1 to 3 weeks", "High", "Easy to medium",
     "Ask venues, suppliers, clients and partners you really work with to list you on their site with a link. Relevant, real, and often a quick yes."),
    ("Local associations, chambers and sponsorships", "2 to 6 weeks", "High", "Medium",
     "Join or sponsor a trade body, chamber of commerce, school, charity or community event that links to its members and sponsors."),
    ("Competitor link gap", "Weeks", "Medium to high", "Medium",
     "Use the Backlink gap tool on the Competitors tab. Sites that already link to several competitors are proven, relevant targets."),
    ("Local news and press", "Weeks", "High", "Hard",
     "Pitch a genuine local story: an event, an opening, a community effort. Not guaranteed, but one good link can outweigh dozens of weak ones."),
    ("Guest articles on relevant local blogs", "Weeks", "Medium to high", "Medium",
     "Offer something useful to a blog your customers read. Never pay for placement on a network of sites that sell posts."),
    ("A resource others want to cite", "Months", "High", "Hard",
     "A local guide, price survey or checklist that is better than what exists. Slow, but it keeps earning links."),
]
AVOID = ["Buying link packages that promise hundreds of backlinks",
         "Private blog networks and sites that openly sell guest posts",
         "Comment, forum or profile spam", "Large-scale link exchanges"]
INDUSTRY_TIPS = {
    "health": "Ask hospitals, doctors and associations you work with for referral or partner-page links. Local sports clubs and gyms are good fits for physiotherapy.",
    "wedding": "Venues, decorators, photographers and planners you work with often have vendor pages. Wedding directories convert well.",
    "home": "Suppliers, property managers, builders and housing societies are natural link partners.",
    "b2b": "Industry associations, supplier directories and trade shows publish member and exhibitor lists with links.",
    "general": "Start with your suppliers, customers and local organisations, then add directories.",
}


def for_region(country, industry="general"):
    inds = {"general", industry}
    dirs = [d for d in REGIONAL.get(country, []) if d[2] in inds]
    to_dict = lambda d: {"name": d[0], "url": d[1], "type": INDUSTRIES.get(d[2], d[2]), "note": d[3]}
    return {
        "global": [to_dict(d) for d in GLOBAL],
        "regional": [to_dict(d) for d in dirs],
        "region_known": country in REGIONAL,
        "strategies": [dict(zip(("name", "speed", "quality", "effort", "how"), s)) for s in STRATEGIES],
        "avoid": AVOID, "tip": INDUSTRY_TIPS.get(industry, INDUSTRY_TIPS["general"]),
        "note": "Directories change. Check each one is active and read its listing terms before you submit.",
    }
