"""Region polygons from the NVE Atlas shapefiles, and random locations inside them."""

from functools import lru_cache
from pathlib import Path

import geopandas as gpd
import pandas as pd

# Paths from the repo root, so they work from both the notebook and the app
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
PRICE_AREAS_SHP = DATA_DIR / "Budområder" / "Budområder.shp"
NVE_REGIONS_SHP = DATA_DIR / "NVE_Region" / "NVE_Region.shp"

# East = RØ + RS, West = RV, North = RM + RN
VASS_REGIONS = {"VASS1": ["RØ", "RS"], "VASS2": ["RV"], "VASS3": ["RM", "RN"]}

# UTM 33N, same as the shapefiles
PROJECTED_CRS = "EPSG:25833"


def read_layer(path: Path) -> gpd.GeoDataFrame:
    """Read a shapefile in the projected CRS."""
    return gpd.read_file(path, encoding="utf-8").to_crs(PROJECTED_CRS)


def build_regions(
    price_areas_path: Path = PRICE_AREAS_SHP, nve_regions_path: Path = NVE_REGIONS_SHP
) -> gpd.GeoDataFrame:
    """One polygon per region: NO1-NO5, VASS1-VASS3 and NO (all of Norway)."""
    price_areas = read_layer(price_areas_path)
    nve = read_layer(nve_regions_path)

    # The price areas reach further out to sea than the NVE regions, so clipping them
    outline = nve.dissolve()[["geometry"]]

    # "NO 1" -> "NO1"
    price_areas["region"] = price_areas["budomr"].str.replace(" ", "")
    price_areas = gpd.clip(price_areas.dissolve(by="region").reset_index()[["region", "geometry"]], outline)

    # Merge the NVE regions into the three VASS regions
    vass = []
    for region, codes in VASS_REGIONS.items():
        geometry = nve.loc[nve["REGION"].isin(codes)].union_all()
        vass.append({"region": region, "geometry": geometry})
    vass = gpd.GeoDataFrame(vass, crs=PROJECTED_CRS)

    # The whole outline is the national region
    national = outline.assign(region="NO")[["region", "geometry"]]
    regions = pd.concat([price_areas, vass, national], ignore_index=True)
    return gpd.GeoDataFrame(regions, crs=PROJECTED_CRS)


def sample_locations(regions: gpd.GeoDataFrame, n: int = 1000, seed: int = 42) -> pd.DataFrame:
    """`n` random points per region as lon/lat, sampled in metres so they are even by area."""
    frames = []
    for i, (region, geometry) in enumerate(zip(regions["region"], regions.geometry)):
        points = gpd.GeoSeries([geometry], crs=regions.crs).sample_points(n, rng=seed + i)
        points = points.explode(index_parts=False).to_crs("EPSG:4326")
        frames.append(pd.DataFrame({"region": region, "lon": points.x, "lat": points.y}))
    return pd.concat(frames, ignore_index=True)


@lru_cache
def region_locations(n: int = 1000, seed: int = 42) -> pd.DataFrame:
    """The sampled locations for all regions, built once per process.
    
    The fixed seed gives the notebook and the app the same points without storing them.
    """
    return sample_locations(build_regions(), n=n, seed=seed).round(5)   # 5 decimals ≈ 1 m
