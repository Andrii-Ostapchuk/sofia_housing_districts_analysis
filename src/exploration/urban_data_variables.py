"""
Defines the variables from https://urbandata.sofia.bg/ website.
"""

import pandas as pd
import geopandas as gpd

# Gets the folder directory where urban data is located to avoid duplication
folder = r'D:\Data Analysis\5_Projects\sofia_housing_districts_analysis\data\sofia_data\urbandata_sofia_bg'

# Reads files from urban data
districts = gpd.read_file(folder + r'\natovarv_sasht_polojenie_kk_072020_26_sofpl_20201118.geojson')
district_codes = gpd.read_file(folder + r'\districts_26_nag_20170101.geojson')

kindergartens = gpd.read_file(folder + r'\dg_points_26_sofpr_20180808.geojson')
schools = gpd.read_file(folder + r'\uchilishta_points_26_sofpr_20180808.geojson')

parking_spaces = gpd.read_file(folder + r'\parkomesta_25_cgm_20200900.geojson')

parks_catchment_areas = gpd.read_file(folder + r'\parkove_400_800_1200_2000m_25_sofpr_20190000.geojson')
public_transport_catchment_areas = gpd.read_file(folder + r'\dostup_mgt_all_400_600_800m_overlap_20210300.geojson')


healthcare_coverage = gpd.read_file(folder + r'\dkc_obsl_naselenie_grao_25_sofpl_20210100.geojson')




