"""
Live Multi-Store Book Price Comparator
Searches across 17 Bangladeshi Bookstores in Real-Time:
--- 7 Islamic Bookstores ---
1. AladaBoi (aladaboi.com)
2. Ruhama Shop (ruhamashop.com)
3. BDBooks (bdbooks.net)
4. Wafilife (wafilife.com)
5. Kitabghor (kitabghor.com)
6. Maktabatul Ashraf (maktabatulashraf.com)
7. BoiBitan (boibitan.com)

--- 10 General / Academic / Literary Bookstores ---
8. Baatighar (baatighar.com)
9. Boibari (boibari.com)
10. eBoighar (eboighar.com)
11. Adarsha (adarsha.com.bd)
12. BookTankBD (booktankbd.com)
13. BookOceanBD (bookoceanbd.com)
14. Bengal Publications (bengalpublications.com)
15. PBS (pbs.com.bd)
16. Prothoma (prothoma.com)
17. Rokomari (rokomari.com)
"""
import sys
import os

from app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"🚀 Starting Live 17-Store Book Price Comparator on http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
