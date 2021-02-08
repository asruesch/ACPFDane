# Runoff Delivery Ratio
# M. Diebel, Dane County LWRD diebel.matthew@countyofdane.com
# August 2020

# This script takes a HUC12 LiDAR DEM as input and conducts the following analyses:
# Run ACPF tools:
    # Hydro conditioning: Cut DEM with culvert lines, fill depressions, calculate flow direction and accumulation.
    # Flow paths: Define flow paths with 10 acre flow accumulation.
    # Depressions: Define depressions in DEM above 20,000 sq ft in surface area.
# Refine HUC12 boundary
# Delineate flow path and depression watersheds
# Define watershed topology through node intersections and LakeCat tool
# Loop through design storms
    # Loop through watersheds to calculate incremental and cumulative runoff with curve number hydrology
    # Loop through watersheds to calculate downstream runoff ratio
# Calculate unit stream power of flow paths

###############################################################################
# Add the following layers (with the specified names) to an ArcGIS Pro project:
    # "dem" (uncut, unfilled) for ACPF buffered watershed
    # "cutLines" (culvert lines)
    # "depOutlets" (depression outlet points from preliminary analysis, if applicable)
    # "CNlow" (runoff curve number raster)
    # "gSSURGO" (version from ACPF database)

# Specify path to geodatabase:
path = "C:/LWRD/Yahara_CLEAN/flow_paths/databases/acpf070900020902.gdb"

exec(open("C:/LWRD/Miscellaneous/ArcGIS/ACPF_V3_Pro/Scripts/DeliveryRatioFunctions.py").read())

arcpy.HydroConditioning("cutLines", None, "dem", os.path.join(path, "demCut"), os.path.join(path, "demFill"), os.path.join(path, "D8FlowDir"), os.path.join(path, "D8FlowAcc"), os.path.join(path, "Hshd"), 0.01)

arcpy.FlowPaths("D8FlowAcc", "D8FlowDir", 10, os.path.join(path, "flowPaths"))

arcpy.DepressionVolume("demCut", "demFill", "gSSURGO", 0.01, 0.459, os.path.join(path, "Depressions"))

deleteFalseDepressions()

# Leave "stub" flowLines on all inlets and outlets, and delete flowLines that connect to those stubs; Save Edits
# Select any reach in watershed from flowPaths

findConnected()

# Check selection for accuracy

refineHUC12()

# Delete pathWatersheds that are upstream of watershed inlet or downstream of watershed outlet

pruneDepressions()

pruneFlowPaths()

# Sort flowPaths by DepressID, then for each DepressID:
    # Delete all but one flowPath that exits the depression, then
    # Merge remaining path with next downstream path (i.e., remove pseudonodes)

defineTopology()

watershedSeeds()

watershed()

watershedPolygons()

LakeCat()

watershedAttributes()

# Delete watershedsPoly and flowPaths that are upstream or downstream of watershed boundary.
# Edit TO_ID of outlet flowPath and watershedsPoly to Null
# Check that all watersheds except outlet have a TO_ID

runoff()

# Map RORDS to check topology

makeTransects()

# R Manning Test Script

joinUSP()

RelativeElevation()