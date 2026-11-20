# SMART ROUTE — JAIN Local Places & Road-Quality Update

This update adds a JAIN Global Campus / Jakkasandra / Harohalli directory and more careful route presentation.

## What's included

- A focused directory of restaurants, cafes/bakeries, hotels, PGs/hostels and JAIN campus access.
- Search-on-demand for directory businesses through the existing FastAPI `/api/search` endpoint, biased to the JAIN Main Gate.
- The directory refuses to invent a map coordinate: if Photon/OpenStreetMap does not return a match within 18 km of JAIN Global Campus, it leaves the place unpinned and offers an external map search link.
- Existing Plus Code-based pins are labelled approximate and should be checked against the actual building entrance.
- The JAIN Main Gate is the recommended road-access point. The campus-ground reference and the DSU campus/building reference are marked as non-road-access references in the popups.
- Dynamic OpenStreetMap place categories now distinguish hotels from hostels/PGs.
- Optional road overlay filters cover main roads, local/residential streets, service roads, and mapped tracks, paths, footways, cycleways, and pedestrian ways.
- Route preference selector wired to the backend: Prefer named roads, Balanced route, or Fastest route.
- Alternative comparison includes distance, estimated time, and road-name/reference-tag coverage.
- The backend uses OSRM's `radiuses` parameter (150 m by default) to limit how far route endpoints may snap to a mapped road, and requests up to three route alternatives where available.
- The route panel explains the OSRM engine and the application's own alternative-ranking formulas. The hosted provider's active CH/MLD search mode is not exposed by its public response.
- Route details show the proportion of named/reference-tagged versus unnamed route-step distance and flags unnamed segments.


## India-wide map and routing

The Route Planner opens at an India overview and provides quick views for 20 major Indian cities plus a selector for all 28 states and 8 union territories. The city and state controls only move the map; actual roads, map labels and place data are loaded from the underlying services.

- **Map tiles:** OpenStreetMap and the alternate tile styles provide global map coverage. The base map is not limited to the Bengaluru directory.
- **Place search:** Photon is a global geocoder. The map centre is sent as a relevance hint; it is not intended to restrict search to Bengaluru or to India.
- **Road and place details:** OpenStreetMap data is queried for the current visible map area. Detailed place markers load at city/neighbourhood zoom; the optional road overlay loads mapped street and path geometries at closer zoom.
- **Routing:** The FOSSGIS public OSRM service documents worldwide car, bicycle and foot profiles. Routes can still fail where mapped roads are disconnected, access-restricted or missing. Island, mountain, rural and border areas may have uneven routing coverage.
- **Local directory:** Curated JAIN / Jakkasandra / Harohalli pins are regional demonstration data. They are now hidden by default and can be enabled separately; they do not define the map's geographic coverage.

The public Photon, Overpass and FOSSGIS services are shared, best-effort services. Use viewport-based requests, respect their usage policies, and do not treat them as production SLAs. OpenStreetMap data is community maintained and can be incomplete or out of date. Keep all required attribution visible.

## Automated checks

The repository includes standard-library `unittest` tests for request validation, route normalisation and the alternative-ranking formulas. GitHub Actions runs these tests on pushes to `master` and `feature/**`, and on pull requests targeting `master`.

Run them locally from the repository root:

```powershell
python -m pip install -r backend/requirements.txt
python -m unittest discover -s backend/tests -v
```

## Authentication and request flow

### Does this repository implement authentication?

No. The current project has no user accounts, login/logout flow, password storage, session cookies, JWTs, OAuth flow, bearer tokens, API keys, or refresh tokens. The browser calls the project's FastAPI endpoints without an Authorization header. The backend calls public Photon and FOSSGIS OSRM endpoints without API credentials.

The CORS setup in `backend/main.py` is not authentication. It restricts which browser origins may read responses, uses `allow_credentials=False`, and allows the `Content-Type` request header. A non-browser client can still call a publicly reachable API unless deployment-level access controls are added. `FRONTEND_ORIGINS` in `.env` is an origin allow-list, not a secret or token.

### Components

- **Browser UI — `docs/index.html`:** Leaflet displays the map and route geometry. The page sends JSON requests to the FastAPI backend. Map tiles and the optional Overpass road/POI overlays are loaded separately by the browser.
- **API — `backend/main.py`:** FastAPI validates input with Pydantic models and query constraints, applies in-memory caching/rate spacing, and proxies requests to public search and routing services.
- **Place search — Photon:** `GET /api/search` calls Photon/OpenStreetMap and converts GeoJSON features into compact place records.
- **Routing — FOSSGIS-hosted OSRM:** `POST /api/route` validates coordinates and travel profile, requests route geometry and turn steps, then ranks the alternatives using the selected preference.

### Request flow

1. The browser requests `GET /api/search?q=...`. FastAPI validates and normalises the query, checks its five-minute in-memory cache, calls Photon if needed, normalises results, and returns JSON.
2. The user selects a start and destination. The browser posts coordinates, a profile (`driving-car`, `foot-walking`, or `cycling-regular`), and a preference (`named_roads`, `balanced`, or `fastest`) to `POST /api/route`.
3. FastAPI validates the request, selects the matching public OSRM server, applies a bounded snapping radius, requests GeoJSON route geometry, turn steps, and up to three alternatives, then converts the response to the app's feature format.
4. The backend scores the returned alternatives. The browser draws the candidate routes, highlights the selected one, and displays distance, ETA, road-name-tag coverage, and turn-by-turn steps.

### How credentials and tokens are handled

There are currently no application credentials or user tokens to issue, store, refresh, or revoke. The backend sends a descriptive User-Agent header to Photon and OSRM; this identifies the educational client and is not a credential. The local `.env` file only needs `FRONTEND_ORIGINS` for CORS and is excluded by `.gitignore`. Do not put future API secrets in `docs/index.html`, because browser code is visible to visitors.

For a deployment that needs protected user data or actions, add server-validated authentication (for example, secure sessions or OAuth/OIDC), enforce authorization on protected endpoints, and keep provider secrets in server-side environment variables. CORS alone is not an access-control boundary.

## Routing algorithm used by the project

The live map route is calculated by the external **OSRM Route service**, not by the Graph Lab's in-browser Dijkstra/A* demonstrations. OSRM supports **Contraction Hierarchies (CH)** and **Multi-Level Dijkstra (MLD)** routing modes. The current FOSSGIS-hosted endpoint does not expose which mode is enabled, so this repository cannot safely identify its active mode. See the [OSRM project documentation](https://github.com/Project-OSRM/osrm-backend) for supported modes.

Smart Route applies its own ranking after OSRM returns candidate routes:
- **Prefer named roads:** `0.62 × duration ratio + 0.38 × unnamed-distance ratio`.
- **Balanced:** `0.80 × duration ratio + 0.20 × unnamed-distance ratio`.
- **Fastest:** duration ratio only.

This ranks only the candidate routes supplied by OSRM. It does not create roads, guarantee three alternatives, prove that an unnamed segment is unpaved, or establish that a path is open to the selected travel mode. The road overlay is a visual OpenStreetMap layer and is separate from the router's road graph.

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
