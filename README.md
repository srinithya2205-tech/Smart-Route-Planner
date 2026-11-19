# SMART ROUTE — JAIN Local Places & Road-Quality Update

This update adds a JAIN Global Campus / Jakkasandra / Harohalli directory and more careful route presentation.

## What's included

- A focused directory of restaurants, cafes/bakeries, hotels, PGs/hostels and JAIN campus access.
- Search-on-demand for directory businesses through the existing FastAPI `/api/search` endpoint, biased to the JAIN Main Gate.
- The directory refuses to invent a map coordinate: if Photon/OpenStreetMap does not return a match within 18 km of JAIN Global Campus, it leaves the place unpinned and offers an external map search link.
- Existing Plus Code-based pins are labelled approximate and should be checked against the actual building entrance.
- The JAIN Main Gate is the recommended road-access point. The campus-ground reference and the DSU campus/building reference are marked as non-road-access references in the popups.
- Dynamic OpenStreetMap place categories now distinguish hotels from hostels/PGs.
- The optional road-line overlay is less cluttered: it omits `unclassified`, generic `road`, and `service` ways.
- Route preference selector: Prefer named roads, Balanced route, or Fastest route.
- The backend uses OSRM's `radiuses` parameter (150 m by default) to limit how far route endpoints may snap to a mapped road, and requests up to three route alternatives where available.
- Route details show the proportion of named/reference-tagged versus unnamed route-step distance and flags unnamed segments.

## Important limitation about unnamed roads

An unnamed OpenStreetMap way is not necessarily off-road, unpaved, private, or unsafe. It may simply have no `name` or `ref` tag. The public FOSSGIS OSRM profile can still route on some mapped minor roads/tracks. The new `Prefer named roads` setting ranks available alternatives using road-name coverage and travel time; it cannot guarantee that all unnamed or unpaved segments are eliminated. OSRM does not guarantee that alternative routes will always be returned.

If a road is physically inaccessible or incorrectly mapped, please verify it locally and report the map issue to OpenStreetMap. For vehicle access to JAIN, choose the Main Gate, not the campus-ground interior marker.

## Replace files in an existing local project

1. Back up `C:\SmartRoute\docs\index.html` and `C:\SmartRoute\backend\main.py`.
2. Copy this package's `docs\index.html` to `C:\SmartRoute\docs\index.html`.
3. Copy this package's `backend\main.py` to `C:\SmartRoute\backend\main.py`.
4. Keep your existing `backend\.venv` folder and `backend\.env` file. Do not replace either.
5. The `.env` still only needs your existing `FRONTEND_ORIGINS` setting; no routing API key is required for the FOSSGIS OSRM integration.
6. Restart the backend:

   ```powershell
   cd C:\SmartRoute\backend
   .\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
   ```

7. In a second terminal, start the frontend:

   ```powershell
   py -m http.server 5500 --directory "C:\SmartRoute\docs"
   ```

8. Open `http://127.0.0.1:5500/index.html#real`.

## Data and service notes

- JAIN's official contact page lists the campus postal address as JAIN Global Campus, NH 948, Bengaluru–Kanakapura Main Road, Jakkasandra Post, Kanakapura Taluk, Ramanagara District 562112.
- Biriyani Zone's own location page lists its 45th KM Kanakapura Main Road, Jakkasandra/Harohalli address and a dine-in branch.
- Pride Heritage Hotel's contact page lists the Katha No. 398 / 10/298 Kanakapura Main Road address near Dayanand Sagar Hospital.
- Hotel SRS Manor's own site lists its address at Plot 237, Hanumanahally, Cheelur Village, Harohalli.
- Several local restaurant/PG entries are inherited from Plus Code or approximate area references already in the user's project. The UI marks them approximate.
- Public FOSSGIS routing and Photon search services are shared public services; they are suitable for light development and student demonstration, not guaranteed production-scale traffic.

Attribution for the map and map data must remain visible. Do not bulk-download public map tiles.
