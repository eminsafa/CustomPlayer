import pandas as pd
import geopandas as gpd
from shapely.geometry import Point, Polygon
from scipy.spatial import Voronoi
import numpy as np
import folium
import requests
import zipfile
import io
import os
import random
import gzip
import shutil
from tqdm import tqdm

print("Step 1: Initializing...")

# --- DATA DEFINITION ---
airports_data = {
    'LHR': {'name': 'London Heathrow', 'coords': (51.4700, -0.4543)},
    #'LGW': {'name': 'London Gatwick', 'coords': (51.1537, -0.1821)},
    #'STN': {'name': 'London Stansted', 'coords': (51.8850, 0.2350)},
    #'LTN': {'name': 'London Luton', 'coords': (51.8747, -0.3683)},
    #'LCY': {'name': 'London City', 'coords': (51.5054, 0.0553)},
    'MAN': {'name': 'Manchester', 'coords': (53.3614, -2.2747)},
    'BHX': {'name': 'Birmingham', 'coords': (52.4539, -1.7480)},
    #'BRS': {'name': 'Bristol', 'coords': (51.3837, -2.7191)},
    'EDI': {'name': 'Edinburgh', 'coords': (55.9508, -3.3725)},
}

PROJ_CRS = "EPSG:27700"

# --- Step 2 & 3: BOUNDARY AND VORONOI (Unchanged, condensed) ---
print("Step 2 & 3: Loading boundary and calculating Voronoi...")
# (This part is the same as before)
shapefile_path = "ne_10m_admin_1_states_provinces"
if not os.path.exists(shapefile_path):
    url = "https://www.naturalearthdata.com/download/10m/cultural/ne_10m_admin_1_states_provinces.zip"
    r = requests.get(url);
    z = zipfile.ZipFile(io.BytesIO(r.content));
    z.extractall(shapefile_path)
world = gpd.read_file(os.path.join(shapefile_path, "ne_10m_admin_1_states_provinces.shp"))
gb = world[(world['iso_a2'] == 'GB') & (world['name'] != 'Northern Ireland')]
gb_boundary = gb.geometry.union_all()
gb_boundary_proj = gpd.GeoSeries([gb_boundary], crs="EPSG:4326").to_crs(PROJ_CRS).iloc[0]
airport_points = [Point(v['coords'][1], v['coords'][0]) for k, v in airports_data.items()]
gdf_airports = gpd.GeoDataFrame(
    {'iata': list(airports_data.keys()), 'name': [v['name'] for v in airports_data.values()]}, geometry=airport_points,
    crs="EPSG:4326")
gdf_airports_proj = gdf_airports.to_crs(PROJ_CRS)
points_proj = np.array([(p.x, p.y) for p in gdf_airports_proj.geometry])
vor = Voronoi(points_proj)


def voronoi_finite_polygons_2d(vor, radius=None):
    from shapely.geometry import Polygon
    new_regions, new_vertices = [], vor.vertices.tolist()
    center = vor.points.mean(axis=0)
    if radius is None: radius = np.ptp(vor.points, axis=0).max() * 2
    all_ridges = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2));
        all_ridges.setdefault(p2, []).append((p1, v1, v2))
    for p1, region in enumerate(vor.point_region):
        vertices = vor.regions[region]
        if all(v >= 0 for v in vertices): new_regions.append(vertices); continue
        ridges = all_ridges[p1]
        new_region = [v for v in vertices if v >= 0]
        for p2, v1, v2 in ridges:
            if v2 < 0: v1, v2 = v2, v1
            if v1 >= 0: continue
            t = vor.points[p2] - vor.points[p1];
            t /= np.linalg.norm(t);
            n = np.array([-t[1], t[0]])
            midpoint = vor.points[[p1, p2]].mean(axis=0);
            direction = np.sign(np.dot(midpoint - center, n)) * n
            far_point = vor.vertices[v2] + direction * radius
            new_region.append(len(new_vertices));
            new_vertices.append(far_point.tolist())
        vs = np.asarray([new_vertices[v] for v in new_region]);
        c = vs.mean(axis=0);
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = np.asarray(new_region)[np.argsort(angles)];
        new_regions.append(new_region.tolist())
    return new_regions, np.asarray(new_vertices)


regions, vertices = voronoi_finite_polygons_2d(vor)
polygons = [Polygon(vertices[region]).intersection(gb_boundary_proj) for region in regions]
gdf_voronoi = gpd.GeoDataFrame(
    {'iata': gdf_airports_proj['iata'], 'name': gdf_airports_proj['name'], 'geometry': polygons}, crs=PROJ_CRS)

# --- OPTIMIZED POPULATION CALCULATION (Unchanged) ---
print("\nStep 4 & 5: Processing population data...")
pop_gpkg_path = "population_gb.gpkg"
if not os.path.exists(pop_gpkg_path):
    pop_url = "https://geodata-eu-central-1-kontur-public.s3.eu-central-1.amazonaws.com/kontur_datasets/kontur_population_GB_20220630.gpkg.gz"
    pop_gpkg_gz_path = "population_gb.gpkg.gz";
    print(f"-> Downloading population data (approx. 110MB)...")
    with requests.get(pop_url, stream=True) as r:
        r.raise_for_status();
        total_size = int(r.headers.get('content-length', 0))
        with open(pop_gpkg_gz_path, 'wb') as f, tqdm(desc="Downloading", total=total_size, unit='iB', unit_scale=True,
                                                     unit_divisor=1024) as bar:
            for chunk in r.iter_content(chunk_size=8192): bar.update(len(chunk)); f.write(chunk)
    print("-> Decompressing population data...");
    with gzip.open(pop_gpkg_gz_path, 'rb') as f_in, open(pop_gpkg_path, 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    os.remove(pop_gpkg_gz_path)
gdf_pop = gpd.read_file(pop_gpkg_path);
gdf_pop['geometry'] = gdf_pop.geometry.centroid;
gdf_pop_proj = gdf_pop.to_crs(PROJ_CRS)
joined_gdf = gpd.sjoin(gdf_pop_proj, gdf_voronoi, how="inner", predicate="within")
population_by_airport = joined_gdf.groupby('iata')['population'].sum().round(0).astype(int)
gdf_voronoi = gdf_voronoi.merge(population_by_airport, on='iata', how='left').fillna(0)

# --- DISPLAY RESULTS AND CREATE MAP ---
print("\n--- Population by Airport Catchment Area (Approximation) ---")
print(gdf_voronoi[['name', 'population']].sort_values('population', ascending=False).to_string(index=False))
print("-----------------------------------------------------------\n")

print("Step 6: Creating interactive map with permanent labels...")
gdf_voronoi_wgs84 = gdf_voronoi.to_crs("EPSG:4326")

map_center = [54.5, -3.4];
m = folium.Map(location=map_center, zoom_start=6, tiles="CartoDB positron")
colors = {iata: f"#{random.randint(0, 0xFFFFFF):06x}" for iata in gdf_voronoi_wgs84['iata'].unique()}

# Add the colored polygons to the map (WITHOUT the tooltip)
folium.GeoJson(
    gdf_voronoi_wgs84,
    style_function=lambda feature: {'fillColor': colors[feature['properties']['iata']], 'color': 'black', 'weight': 1.5,
                                    'fillOpacity': 0.6},
).add_to(m)

# --- NEW SECTION: ADD PERMANENT LABELS ---
# Loop through the regions to add a text label to the center of each one.
for idx, row in gdf_voronoi_wgs84.iterrows():
    # Find a guaranteed-internal point to place the label
    point = row.geometry.representative_point()

    # Shorten long airport names for clarity (e.g., "London Heathrow" -> "Heathrow")
    short_name = row['name'].replace("London ", "")

    # Create the custom HTML for the label
    label_html = f"""
    <div style="font-family: Arial, sans-serif; font-size: 11pt; font-weight: bold; color: #111; text-shadow: 1px 1px 2px #fff;">
        <div style="text-align: center;">{short_name}</div>
        <div style="font-size: 9pt; font-weight: normal; text-align: center;">{int(row['population']):,}</div>
    </div>
    """

    # Create a DivIcon and add it as a marker
    folium.Marker(
        location=[point.y, point.x],
        icon=folium.DivIcon(
            icon_size=(150, 40),
            icon_anchor=(75, 20),  # Anchor to the center of the text box
            html=label_html
        )
    ).add_to(m)

# Add the original airport markers (the plane icons)
for idx, row in gdf_airports.iterrows():
    folium.Marker(location=[row.geometry.y, row.geometry.x], popup=f"<strong>{row['name']} ({row['iata']})</strong>",
                  icon=folium.Icon(color='black', icon='plane', prefix='fa')).add_to(m)

folium.LayerControl().add_to(m)
output_filename = "airport_voronoi_map_with_population_labels.html"
m.save(output_filename)

print(f"Map saved to {output_filename}")
print("Done!")