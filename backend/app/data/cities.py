"""Reference cities used to place synthetic assets, population and vehicles.

Population figures are approximate urban-agglomeration sizes (Census 2011 /
recent estimates, rounded). They only seed the synthetic population surface.
"""

CITIES = [
    # name, state, lat, lon, population, urban sigma (km)
    ("Bengaluru", "Karnataka", 12.9716, 77.5946, 12_300_000, 14),
    ("Mumbai", "Maharashtra", 19.0760, 72.8777, 20_400_000, 13),
    ("Delhi", "Delhi", 28.6139, 77.2090, 29_000_000, 18),
    ("Chennai", "Tamil Nadu", 13.0827, 80.2707, 10_900_000, 13),
    ("Kolkata", "West Bengal", 22.5726, 88.3639, 14_900_000, 13),
    ("Hyderabad", "Telangana", 17.3850, 78.4867, 10_000_000, 14),
    ("Bhubaneswar", "Odisha", 20.2961, 85.8245, 1_200_000, 8),
    ("Puri", "Odisha", 19.8135, 85.8312, 300_000, 5),
    ("Visakhapatnam", "Andhra Pradesh", 17.6868, 83.2185, 2_200_000, 9),
    ("Guwahati", "Assam", 26.1445, 91.7362, 1_100_000, 8),
    ("Ahmedabad", "Gujarat", 23.0225, 72.5714, 8_400_000, 12),
    ("Jaipur", "Rajasthan", 26.9124, 75.7873, 4_100_000, 10),
    ("Kochi", "Kerala", 9.9312, 76.2673, 2_100_000, 9),
    ("Mysuru", "Karnataka", 12.2958, 76.6394, 1_100_000, 7),
    ("Pune", "Maharashtra", 18.5204, 73.8567, 7_200_000, 11),
    ("Lucknow", "Uttar Pradesh", 26.8467, 80.9462, 3_900_000, 10),
    ("Patna", "Bihar", 25.5941, 85.1376, 2_500_000, 9),
    ("Nagpur", "Maharashtra", 21.1458, 79.0882, 2_900_000, 9),
]

CITY_BY_NAME = {c[0]: c for c in CITIES}

CITY_CODE = {
    "Bengaluru": "BLR", "Mumbai": "MUM", "Delhi": "DEL", "Chennai": "CHN", "Kolkata": "KOL",
    "Hyderabad": "HYD", "Bhubaneswar": "BBS", "Puri": "PUR", "Visakhapatnam": "VTZ", "Guwahati": "GUW",
    "Ahmedabad": "AMD", "Jaipur": "JAI", "Kochi": "COK", "Mysuru": "MYS", "Pune": "PNQ",
    "Lucknow": "LKO", "Patna": "PAT", "Nagpur": "NAG",
}

# Neighbourhoods used to give demo institutions unique, realistic names
# (Bengaluru uses the Census BBMP ward names instead).
LOCALITIES = {
    "Mumbai": ["Andheri", "Bandra", "Dadar", "Kurla", "Chembur", "Borivali", "Malad", "Goregaon", "Ghatkopar", "Colaba", "Worli", "Powai"],
    "Delhi": ["Karol Bagh", "Dwarka", "Rohini", "Saket", "Lajpat Nagar", "Janakpuri", "Mayur Vihar", "Pitampura", "Vasant Kunj", "Shahdara", "Laxmi Nagar", "Model Town"],
    "Chennai": ["T. Nagar", "Adyar", "Anna Nagar", "Velachery", "Mylapore", "Tambaram", "Guindy", "Porur", "Perambur", "Egmore"],
    "Kolkata": ["Salt Lake", "Howrah", "Ballygunge", "Behala", "Dum Dum", "Park Circus", "Jadavpur", "Tollygunge", "Garia", "Shyambazar"],
    "Hyderabad": ["Banjara Hills", "Secunderabad", "Kukatpally", "Gachibowli", "Ameerpet", "Dilsukhnagar", "Madhapur", "Begumpet", "Charminar", "LB Nagar"],
    "Bhubaneswar": ["Saheed Nagar", "Patia", "Nayapalli", "Khandagiri", "Chandrasekharpur", "Old Town", "Rasulgarh", "Jaydev Vihar"],
    "Puri": ["Grand Road", "Swargadwar", "Baliapanda", "Chakratirtha", "Penthakata"],
    "Visakhapatnam": ["MVP Colony", "Gajuwaka", "Dwaraka Nagar", "Madhurawada", "Seethammadhara", "Pendurthi", "Rushikonda"],
    "Guwahati": ["Dispur", "Paltan Bazaar", "Beltola", "Chandmari", "Maligaon", "Six Mile", "Zoo Road", "Ganeshguri"],
    "Ahmedabad": ["Navrangpura", "Maninagar", "Satellite", "Bopal", "Vastrapur", "Naroda", "Chandkheda", "Paldi", "Ghatlodia"],
    "Jaipur": ["Malviya Nagar", "Mansarovar", "Vaishali Nagar", "C-Scheme", "Raja Park", "Jhotwara", "Sanganer", "Tonk Road"],
    "Kochi": ["Edappally", "Kakkanad", "Vyttila", "Fort Kochi", "Kaloor", "Palarivattom", "Thrippunithura", "Aluva"],
    "Mysuru": ["Vijayanagar", "Kuvempunagar", "Saraswathipuram", "Jayalakshmipuram", "Hebbal", "Nazarbad", "Gokulam"],
    "Pune": ["Kothrud", "Hadapsar", "Shivajinagar", "Aundh", "Baner", "Hinjewadi", "Wakad", "Kharadi", "Viman Nagar", "Swargate"],
    "Lucknow": ["Hazratganj", "Gomti Nagar", "Aliganj", "Indira Nagar", "Alambagh", "Chowk", "Aminabad", "Jankipuram"],
    "Patna": ["Boring Road", "Kankarbagh", "Rajendra Nagar", "Patliputra", "Danapur", "Bailey Road", "Ashok Rajpath"],
    "Nagpur": ["Sitabuldi", "Dharampeth", "Sadar", "Manish Nagar", "Wardhaman Nagar", "Hingna", "Civil Lines", "Pratap Nagar"],
}
