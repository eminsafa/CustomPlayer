import geopandas as gpd
import matplotlib.pyplot as plt
from shapely.geometry import Point, Polygon
from scipy.spatial import Voronoi, voronoi_plot_2d
import numpy as np

# Airport coordinates: (Name, Longitude, Latitude)
airports = {
    "Heathrow": (-0.4543, 51.4700),
    "Gatwick": (-0.1821, 51.1537),
    "Luton": (-0.3768, 51.8787),
    "Stansted": (0.2350, 51.8840),
    "London City": (0.0553, 51.5053),
    "Bristol": (-2.7191, 51.3827),
    "Manchester": (-2.2700, 53.3659),
    "Birmingham": (-1.7480, 52.4539),
    "Edinburgh": (-3.3725, 55.9500),
}

# Load UK map
world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
uk = world[(world.name == "United Kingdom")]

# Prepare airport points
coords = np.array(list(airports.values()))
names = list(airports.keys())

# Voronoi generation
vor = Voronoi(coords)

# Plotting
fig, ax = plt.subplots(figsize=(10, 15))
uk.plot(ax=ax, color='white', edgecolor='black')

# Color Voronoi regions
for region_index in vor.point_region:
    region = vor.regions[region_index]
    if -1 in region or len(region) == 0:
        continue
    polygon = [vor.vertices[i] for i in region]
    poly = Polygon(polygon)
    if poly.is_valid:
        plt.fill(*zip(*polygon), alpha=0.3)

# Plot airports
for name, (lon, lat) in airports.items():
    plt.plot(lon, lat, 'ko')
    plt.text(lon + 0.1, lat + 0.1, name, fontsize=9)

ax.set_xlim(-8, 2)
ax.set_ylim(49.5, 59)
ax.set_title("UK Airport Coverage Map (Voronoi Diagram)")
plt.xlabel("Longitude")
plt.ylabel("Latitude")
plt.grid(True)
plt.show()
