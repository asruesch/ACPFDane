# Import modules and scripts
import arcpy
from arcpy import env
from arcpy.sa import *
from copy import copy
import sys, string, os, time
import numpy as np
import pandas as pd
import rasterio as rs
arcpy.CheckOutExtension("Spatial")
arcpy.ImportToolbox("acpf_V3_Pro.tbx") # modified versions of FlowPaths and DepressionVolume tools
storms = pd.read_csv("design_storms.csv")
exec(open("LakeCat_findFlows.py").read()) # from https://github.com/USEPA/LakeCat/blob/master/LakeCat_functions.py

# Set environments
arcpy.env.extent = os.path.join(path, "dem")
arcpy.env.snapRaster = os.path.join(path, "dem")
arcpy.env.overwriteOutput = True

# Select connected flow paths
def findConnected():
    i = 0
    j = 1
    while True:
        arcpy.SelectLayerByLocation_management("flowPaths", "INTERSECT", "flowPaths", "", "ADD_TO_SELECTION")
        j = int(arcpy.GetCount_management("flowPaths")[0])
        if j == i:
            break
        else:
            i = j

# Delete depressions based on depOutlets codes: stormsewer and land use
def deleteFalseDepressions():
    arcpy.SelectLayerByAttribute_management("depOutlets", "CLEAR_SELECTION")
    arcpy.management.SelectLayerByAttribute("depOutlets", "NEW_SELECTION", "CheckCode = '6' Or CheckCode = '7'", None)
    arcpy.management.SelectLayerByLocation("Depressions", "INTERSECT", "depOutlets", None, "NEW_SELECTION", "NOT_INVERT")
    arcpy.DeleteFeatures_management("Depressions")
    arcpy.SelectLayerByAttribute_management("depOutlets", "CLEAR_SELECTION")

# Use flow path watershed to refine HUC12 boundary
def refineHUC12():
    arcpy.SelectLayerByAttribute_management("flowPaths", "SWITCH_SELECTION")
    arcpy.DeleteFeatures_management("flowPaths")
    arcpy.conversion.FeatureToRaster("flowPaths", "grid_code", os.path.join(path, "pathSeeds"), 2)
    arcpy.env.parallelProcessingFactor = "100%"
    pathWatersheds = arcpy.sa.Watershed("D8FlowDir", "pathSeeds", "Value")
    arcpy.env.parallelProcessingFactor = ""
    arcpy.RasterToPolygon_conversion(pathWatersheds, os.path.join(path, "pathWatershedsPoly"), "NO_SIMPLIFY")
    del pathWatersheds
    arcpy.Delete_management(os.path.join(path,"pathSeeds"))

# Delete depressions that are outside of pathWatersheds extent
def pruneDepressions():
    arcpy.SelectLayerByAttribute_management("Depressions", "CLEAR_SELECTION")
    allDepCount = int(arcpy.GetCount_management("Depressions")[0])
    arcpy.management.SelectLayerByLocation("Depressions", "HAVE_THEIR_CENTER_IN", "pathWatershedsPoly", None, "NEW_SELECTION", "INVERT")
    selDepCount = int(arcpy.GetCount_management("Depressions")[0])
    if allDepCount > selDepCount and selDepCount > 0:
        arcpy.DeleteFeatures_management("Depressions")
    arcpy.Delete_management(os.path.join(path,"pathWatershedsPoly"))

# Erase sections of flow paths that intersect depressions
def pruneFlowPaths():
    arcpy.management.CopyFeatures("flowPaths", os.path.join(path, "flowPathsRaw"), None, None, None, None)    
    arcpy.analysis.Erase("flowPathsRaw", "Depressions", os.path.join(path, "flowPathsMP"), None)
    arcpy.management.MultipartToSinglepart("flowPathsMP", os.path.join(path, "flowPaths"))
    arcpy.Delete_management(os.path.join(path,"flowPathsMP"))
    arcpy.management.FeatureVerticesToPoints("flowPaths", os.path.join(path, "flowPathNodes"), "BOTH_ENDS")
    arcpy.analysis.TabulateIntersection("Depressions", "Depress_ID", "flowPathNodes", os.path.join(path, "pathDepIntersect"), "ORIG_FID", None, None, "UNKNOWN")
    arcpy.JoinField_management("flowPaths", "OBJECTID", "pathDepIntersect", "ORIG_FID", ["Depress_ID","PNT_COUNT"])
    arcpy.management.SelectLayerByAttribute("flowPaths", "NEW_SELECTION", "PNT_COUNT = 2", None)
    arcpy.DeleteFeatures_management("flowPaths")
    arcpy.DeleteField_management("flowPaths", ["Depress_ID","PNT_COUNT"])
    arcpy.management.FeatureVerticesToPoints("flowPaths", os.path.join(path, "flowPathNodes"), "START")
    arcpy.management.SelectLayerByLocation("flowPathNodes", "INTERSECT", "Depressions", None, "NEW_SELECTION", "INVERT")
    arcpy.DeleteFeatures_management("flowPathNodes")
    arcpy.analysis.TabulateIntersection("Depressions", "Depress_ID", "flowPathNodes", os.path.join(path, "pathDepIntersect"), "to_node", None, None, "UNKNOWN")
    arcpy.management.SelectLayerByAttribute("pathDepIntersect", "NEW_SELECTION", "PNT_COUNT < 2", None)
    arcpy.management.DeleteRows("pathDepIntersect")
    arcpy.management.JoinField("flowPathNodes", "to_node", "pathDepIntersect", "to_node", "Depress_ID;PNT_COUNT")
    arcpy.management.SelectLayerByAttribute("flowPathNodes", "NEW_SELECTION", "PNT_COUNT IS NULL", None)
    arcpy.DeleteFeatures_management("flowPathNodes")
    arcpy.analysis.SpatialJoin("flowPathNodes", "Depressions", os.path.join(path, "flowPathNodesDepJoin"), "JOIN_ONE_TO_ONE", "KEEP_ALL", 'ORIG_FID "ORIG_FID" true true false 4 Long 0 0,First,#,flowPathsNoDepNodes,ORIG_FID,-1,-1;Depress_ID "Depress_ID" true true false 4 Long 0 0,First,#,flowPathsNoDepNodes,Depress_ID,-1,-1;Depress_ID_1 "Depress_ID_1" true true false 4 Long 0 0,First,#,Depressions,Depress_ID,-1,-1', "INTERSECT", None, None)
    arcpy.management.SelectLayerByAttribute("flowPathNodesDepJoin", "NEW_SELECTION", "Depress_ID <> Depress_ID_1", None)
    arcpy.DeleteFeatures_management("flowPathNodesDepJoin")
    arcpy.JoinField_management("flowPaths", "OBJECTID", "flowPathNodesDepJoin", "ORIG_FID", ["Depress_ID"])
    arcpy.management.SelectLayerByAttribute("flowPaths", "NEW_SELECTION", "Depress_ID IS NOT NULL", None)
    arcpy.sa.ZonalStatisticsAsTable("flowPaths", "grid_code", "D8FlowAcc", arcpy.env.scratchGDB + "\\flowPathAcc", "DATA", "MEAN")
    arcpy.JoinField_management("flowPaths", "grid_code", arcpy.env.scratchGDB + "\\flowPathAcc", "grid_code", ["MEAN"])

# Define topology for all flow paths and depressions that connect to flow paths
def defineTopology():
    arcpy.SelectLayerByAttribute_management("flowPaths", "CLEAR_SELECTION")
    arcpy.DeleteField_management("flowPaths", ["arcid","grid_code","from_node","to_node","grid_code_to","ORIG_FID","Depress_ID","MEAN"])
    arcpy.management.FeatureVerticesToPoints("flowPaths", os.path.join(path, "flowPathNodesUS"), "START")
    arcpy.management.FeatureVerticesToPoints("flowPaths", os.path.join(path, "flowPathNodesDS"), "END")
    arcpy.management.AddGeometryAttributes("flowPathNodesUS", "POINT_X_Y_Z_M", None, None, None)
    arcpy.management.AddGeometryAttributes("flowPathNodesDS", "POINT_X_Y_Z_M", None, None, None)
    arcpy.AddField_management("flowPathNodesUS", "LONLAT", "DOUBLE")
    arcpy.AddField_management("flowPathNodesDS", "LONLAT", "DOUBLE")
    arcpy.management.CalculateField("flowPathNodesUS", "LONLAT", "int(!POINT_X!)*10000000 + int(!POINT_Y!)", "PYTHON3", None)
    arcpy.management.CalculateField("flowPathNodesDS", "LONLAT", "int(!POINT_X!)*10000000 + int(!POINT_Y!)", "PYTHON3", None)
    arcpy.JoinField_management("flowPathNodesDS", "LONLAT", "flowPathNodesUS", "LONLAT", ["ORIG_FID"])
    arcpy.AlterField_management("flowPathNodesDS", "ORIG_FID", "FROM_ID", "FROM_ID")
    arcpy.AlterField_management("flowPathNodesDS", "ORIG_FID_1", "TO_ID", "TO_ID")
    arcpy.analysis.SpatialJoin("flowPathNodesDS", "Depressions", os.path.join(path, "flowPathNodesDSDep"), "JOIN_ONE_TO_ONE", "KEEP_ALL", 'FROM_ID "FROM_ID" true true false 4 Long 0 0,First,#,flowPathNodesDS,FROM_ID,-1,-1;TO_ID "TO_ID" true true false 4 Long 0 0,First,#,flowPathNodesDS,TO_ID,-1,-1;Depress_ID "Depress_ID" true true false 4 Long 0 0,First,#,Depressions,Depress_ID,-1,-1', "INTERSECT", None, None)
    arcpy.management.SelectLayerByAttribute("flowPathNodesDSDep", "NEW_SELECTION", "TO_ID IS NULL", None)
    arcpy.management.CalculateField("flowPathNodesDSDep", "TO_ID", "!Depress_ID!", "PYTHON3", None)
    arcpy.SelectLayerByAttribute_management("flowPathNodesDSDep", "CLEAR_SELECTION")
    arcpy.AlterField_management("flowPathNodesUS", "ORIG_FID", "TO_ID", "TO_ID")
    arcpy.analysis.SpatialJoin("flowPathNodesUS", "Depressions", os.path.join(path, "flowPathNodesUSDep"), "JOIN_ONE_TO_ONE", "KEEP_ALL", 'TO_ID "TO_ID" true true false 4 Long 0 0,First,#,flowPathNodesUS,TO_ID,-1,-1;Depress_ID "Depress_ID" true true false 4 Long 0 0,First,#,Depressions,Depress_ID,-1,-1', "INTERSECT", None, None)
    # Join node topology to flow paths and depressions
    arcpy.AddField_management("flowPaths", "FROM_ID", "LONG")
    arcpy.management.CalculateField("flowPaths", "FROM_ID", "!OBJECTID!", "PYTHON3", None)
    arcpy.JoinField_management("flowPaths", "FROM_ID", "flowPathNodesDSDep", "FROM_ID", ["TO_ID"])
    arcpy.JoinField_management("Depressions", "Depress_ID", "flowPathNodesUSDep", "Depress_ID", ["TO_ID"])
    # Delete node layers
    arcpy.Delete_management(os.path.join(path,"flowPathNodesUS"))
    arcpy.Delete_management(os.path.join(path,"flowPathNodesDS"))
    arcpy.Delete_management(os.path.join(path,"flowPathNodesUSDep"))
    arcpy.Delete_management(os.path.join(path,"flowPathNodesDSDep"))
    arcpy.Delete_management(os.path.join(path,"flowPathNodes"))
    arcpy.Delete_management(os.path.join(path,"flowPathNodesDepJoin"))
    arcpy.Delete_management(os.path.join(path,"pathDepIntersect"))
    arcpy.Delete_management(arcpy.env.scratchGDB + "\\flowPathAcc")
    arcpy.Delete_management(os.path.join(path,"Hshd"))

# Convert flow paths and depressions to rasters and combine to make seeds
def watershedSeeds():
    arcpy.conversion.FeatureToRaster("flowPaths", "FROM_ID", os.path.join(path, "pathSeeds"), 2)
    arcpy.conversion.FeatureToRaster("Depressions", "Depress_ID", os.path.join(path, "depSeeds"), 2)
    seeds = Con(IsNull("depSeeds"), "pathSeeds", "depSeeds")
    seeds.save(os.path.join(path, "seeds"))
    arcpy.Delete_management(os.path.join(path,"depSeeds"))
    arcpy.Delete_management(os.path.join(path,"pathSeeds"))

# Delineate watersheds for seeds
def watershed():
    arcpy.env.parallelProcessingFactor = "100%"
    watersheds = arcpy.sa.Watershed("D8FlowDir", os.path.join(path, "seeds"), "Value")
    arcpy.env.parallelProcessingFactor = ""
    watersheds.save(os.path.join(path,"watersheds"))
    arcpy.Delete_management(os.path.join(path,"seeds"))
    
# Convert watershed raster to polygons
def watershedPolygons():
    arcpy.RasterToPolygon_conversion(os.path.join(path, "watersheds"), os.path.join(path, "watershedsPoly"), "NO_SIMPLIFY", "Value", "MULTIPLE_OUTER_PART")
    
# Run watershed topology script from LakeCat
def LakeCat():
    zone_file = os.path.join(arcpy.env.scratchFolder, "watersheds.tif")
    arcpy.CopyRaster_management(os.path.join(path, "watersheds"), zone_file)
    fdr_file = os.path.join(arcpy.env.scratchFolder, "D8FlowDir.tif")
    arcpy.CopyRaster_management(os.path.join(path, "D8FlowDir"), fdr_file)
    df = findFlows(zone_file, fdr_file)
    arcpy.Delete_management(os.path.join(arcpy.env.scratchFolder, "watersheds.tif"))
    arcpy.Delete_management(os.path.join(arcpy.env.scratchFolder, "D8FlowDir.tif"))
    
    # Convert pandas dataframe to table
    x = np.array(np.rec.fromrecords(df.values))
    names = df.dtypes.index.tolist()
    x.dtype.names = tuple(names)
    arcpy.da.NumPyArrayToTable(x, arcpy.env.scratchGDB + "\\Topology")

# Compile and clean up watershed attributes
def watershedAttributes():
    # Join depression attributes to watersheds
    arcpy.AddField_management("watershedsPoly", "FROM_ID", "LONG")
    arcpy.CalculateField_management("watershedsPoly", "FROM_ID", "!gridcode!") 
    arcpy.JoinField_management("watershedsPoly", "gridcode", "Depressions", "Depress_ID", ["TO_ID"])
    arcpy.JoinField_management("watershedsPoly", "gridcode", "Depressions", "Depress_ID", ["PctHydric","MaxDepthCM","VolAcreFt"])
    arcpy.AddField_management("watershedsPoly", "AreaAcres", "FLOAT")
    arcpy.CalculateField_management("watershedsPoly", "AreaAcres", "!shape.area@acres!") 
    # Join node-based topology to watersheds
    arcpy.JoinField_management("watershedsPoly", "FROM_ID", "flowPaths", "FROM_ID", ["TO_ID"])
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "NEW_SELECTION", "TO_ID IS NULL And TO_ID_1 IS NOT NULL", None)
    arcpy.CalculateField_management("watershedsPoly", "TO_ID", "!TO_ID_1!") 
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "CLEAR_SELECTION")
    arcpy.DeleteField_management("watershedsPoly", ["TO_ID_1"])
    # Join LakeCat topology to watersheds
    arcpy.JoinField_management("watershedsPoly", "gridcode", arcpy.env.scratchGDB + "\\Topology", "FROMCOMID", ["TOCOMID"])
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "NEW_SELECTION", "TO_ID IS NULL And TOCOMID IS NOT NULL", None)
    arcpy.CalculateField_management("watershedsPoly", "TO_ID", "!TOCOMID!") 
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "CLEAR_SELECTION")
    arcpy.DeleteField_management("watershedsPoly", ["Id","gridcode","TOCOMID"])
    # Replace path-based TO_IDs that have no watershed with next downstream TO_ID
    arcpy.management.CopyRows("watershedsPoly", arcpy.env.scratchGDB + "\\watersheds", None)
    arcpy.JoinField_management("watershedsPoly", "TO_ID", arcpy.env.scratchGDB + "\\watersheds", "FROM_ID", ["FROM_ID"])
    arcpy.JoinField_management("watershedsPoly", "TO_ID", "flowPaths", "FROM_ID", ["FROM_ID","TO_ID"])
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "NEW_SELECTION", "FROM_ID_1 IS NULL And TO_ID IS NOT NULL", None)
    arcpy.CalculateField_management("watershedsPoly", "TO_ID", "!TO_ID_1!") 
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "CLEAR_SELECTION")
    # Clean up
    arcpy.DeleteField_management("watershedsPoly", ["FROM_ID_1","FROM_ID_12","TO_ID_1"])
    arcpy.Delete_management(arcpy.env.scratchGDB + "\\Topology")
    arcpy.Delete_management(arcpy.env.scratchGDB + "\\watersheds")
    
# Calculate runoff volumes
def runoff():
    arcpy.SelectLayerByAttribute_management("watershedsPoly", "CLEAR_SELECTION")
    # Calculate mean runoff curve number for watershedsPoly
    arcpy.env.cellSize = "MINOF"
    CNTable = arcpy.sa.ZonalStatisticsAsTable(os.path.join(path, "watersheds"), "Value", "CNlow", arcpy.env.scratchGDB + "\\CNTable", "DATA", "MEAN")
    arcpy.JoinField_management("watershedsPoly", "FROM_ID", arcpy.env.scratchGDB + "\\CNTable", "VALUE", ["MEAN"])
    arcpy.AddField_management("watershedsPoly", "CNlow", "FLOAT")
    arcpy.CalculateField_management("watershedsPoly", "CNlow", "!MEAN!") 
    arcpy.DeleteField_management("watershedsPoly", ["MEAN"])
    
    # Convert watershedsPoly table to pandas dataframe
    arr = arcpy.da.FeatureClassToNumPyArray(os.path.join(path,"watershedsPoly"), ("FROM_ID", "TO_ID", "VolAcreFt", "AreaAcres", "CNlow"), null_value = 0)
    df = pd.DataFrame(arr)
    
    # Sort watersheds in downstream order
    ds = []
    froms = df.FROM_ID[df.TO_ID==0].values.tolist()
    ds.extend(froms)
    while True:
        i = len(ds)
        froms = df.FROM_ID[df.TO_ID.isin(froms)].values.tolist()
        ds.extend(froms)
        j = len(ds)
        if i == j:
            break
    dsdf = pd.DataFrame(ds, columns = ['FROM_ID'])
    dsdf['order'] = dsdf.index
    df2 = pd.merge(df, dsdf, on = "FROM_ID")
    df2 = df2.sort_values(by = 'order', ascending = False)
    df2 = df2.reset_index(drop=True)
    df2['S'] = 0 # 6
    df2['Qraw'] = 0 # 7
    df2['runDep'] = 0  # 8
    df2['runVolS'] = 0 # 9
    df2['runVolT'] = 0 # 10
    df2['runInS'] = 0 # 11
    df2['runOffS'] = 0 # 12
    df2['runInT'] = 0 # 13
    df2['runOffT'] = 0 # 14
    df2['runInNDS'] = 0 # 15
    df2['runInNDT'] = 0 # 16
    df2['RORUS'] = 0 # 17
    df2['RORInc'] = 0 # 18
    df2['RORDS'] = 0 # 19
    
    
    # Loop through design storms
    s = 0
    while s < len(storms):
        P = storms.P[s]
        df2.S = 1000 / df2.CNlow - 10
        df2.Qraw = (P - 0.2 * df2.S)**2 / (P + 0.8 * df2.S)
        df2.loc[P < 0.2 * df2.S, 'runDep'] = 0
        df2.loc[P >= 0.2 * df2.S, 'runDep'] = df2.Qraw / 12
        
        # Loop through watersheds to calculate runIn and runOff
        i = 0
        while i < len(df2):
            us = df2[df2.TO_ID == df2.FROM_ID[i]]
            df2.iloc[i,9] = df2.AreaAcres[i] * df2.runDep[i] 
            df2.iloc[i,10] = df2.runVolT[i] + df2.runVolS[i] * (s + 1)
            df2.iloc[i,11] = df2.AreaAcres[i] * df2.runDep[i] + sum(us.runOffS)
            df2.iloc[i,12] = max(df2.runInS[i] - df2.VolAcreFt[i], 0)
            df2.iloc[i,13] = df2.runInT[i] + df2.runInS[i] * (s + 1)
            df2.iloc[i,14] = df2.runOffT[i] + df2.runOffS[i] * (s + 1)
            df2.iloc[i,15] = df2.runVolS[i] + sum(us.runInNDS)
            df2.iloc[i,16] = df2.runInNDT[i] + df2.runInNDS[i] * (s + 1)
            i += 1
    
        s += 1
        
    df2.RORUS = df2.runOffT / df2.runInNDT
    df2.loc[df2.RORUS.isnull(), 'RORUS'] = 0
        
    # Loop through watersheds to calculate downstream runoff ratio
    df2.loc[df2.runInT == 0, 'RORInc'] = 0
    df2.loc[df2.runInT > 0, 'RORInc'] = df2.runOffT / df2.runInT
    i = 0
    while i < len(df2):
        if df2.runOffT[i] == 0:
            df2.iloc[i,19] = 0
            i += 1
        else:
            ds = [df2.RORInc[i]]
            to = int(df2.TO_ID[i])
            while True:
                RORto = df2.RORInc[df2.FROM_ID == to].values.tolist()
                ds.extend(RORto)
                if to == 0:
                    break
                to = int(df2.TO_ID[df2.FROM_ID == to])
            df2.iloc[i,19] = np.prod(ds)
            i += 1
    
    # Convert pandas dataframe to table
    x = np.array(np.rec.fromrecords(df2.values))
    names = df2.dtypes.index.tolist()
    x.dtype.names = tuple(names)
    arcpy.da.NumPyArrayToTable(x, arcpy.env.scratchGDB + "\\runoff")
    
    # Join runoff table to watershedsPoly
    arcpy.JoinField_management("watershedsPoly", "FROM_ID", arcpy.env.scratchGDB + "\\runoff", "FROM_ID", ["runVolT","runInT","runOffT","RORUS","RORInc","RORDS"])
    arcpy.Delete_management(arcpy.env.scratchGDB + "\\runoff")
    arcpy.Delete_management(arcpy.env.scratchGDB + "\\CNTable")

# Add depression outlets
def depOutlets():
    depMaxFA = arcpy.sa.ZonalStatistics("Depressions", "Depress_ID", "D8FlowAcc", "MAXIMUM", "DATA")
    # break
    maxFA = Con(Raster("D8FlowAcc") == Raster("depMaxFA"), "D8FlowAcc")
    maxFA.save(os.path.join(path, "maxFA"))
    # break
    arcpy.conversion.RasterToPoint("maxFA", os.path.join(path, "depOutlets"), "VALUE")
    arcpy.analysis.SpatialJoin("depOutlets", "RoadCenterline", os.path.join(path,"depOutletsRoads"), "JOIN_ONE_TO_ONE", "KEEP_ALL", 'abvStreetN "abvStreetN" true true false 254 Text 0 0,First,#,RoadCenterline,abvStreetN,0,254', "CLOSEST", "1000 Meters", "RoadDist")
    arcpy.analysis.SpatialJoin("depOutletsRoads", "cutLines", os.path.join(path, "depOutlets"), "JOIN_ONE_TO_ONE", "KEEP_ALL", 'RoadDist "RoadDist" true true false 8 Double 0 0,First,#,depOutletsRoads,RoadDist,-1,-1;abvStreetN "abvStreetN" true true false 254 Text 0 0,First,#,depOutletsRoads,abvStreetN,0,254', "CLOSEST", "1000 Meters", "cutDist")
    arcpy.DeleteField_management("depOutlets", ["Join_Count"])
    arcpy.DeleteField_management("depOutlets", ["TARGET_FID"])

# Unit stream power
def makeTransects():
    # Smoothing doesn't seem to fix the transect orientation issue
    # arcpy.management.CopyFeatures("flowPaths", os.path.join(path,"flowPathsSmooth"), None, None, None, None)
    # arcpy.edit.Generalize("flowPathsSmooth", "6 Meters")
    arcpy.management.GenerateTransectsAlongLines("flowPaths", os.path.join(path,"transects"), "100 Meters", "32 Meters", "END_POINTS")
    arcpy.AlterField_management("transects", "ORIG_FID", "pathID", "pathID")
    # Identify transects that intersect cutLines for later exclusion?
    arcpy.management.GeneratePointsAlongLines("transects", os.path.join(path,"transectPoints"), "DISTANCE", "2 Meters", None, "END_POINTS")
    arcpy.AlterField_management("transectPoints", "ORIG_FID", "transectID", "transectID")
    arcpy.AddField_management("transectPoints", "pointID", "LONG")
    arcpy.CalculateField_management("transectPoints", "pointID", "!OBJECTID!")
    arcpy.DeleteField_management("transectPoints", ["Shape_Length"]) # Delete Shape_Length field so extract values to points will work
    arcpy.sa.ExtractValuesToPoints("transectPoints", os.path.join(path,"demFill"), os.path.join(path,"transectPoints2"), "NONE", "VALUE_ONLY")
    arcpy.AlterField_management("transectPoints2", "RASTERVALU", "Elevation", "Elevation")
    arcpy.conversion.FeatureToRaster("flowPaths", "OBJECTID", os.path.join(path,"flowPathsR"), 2)
    arcpy.sa.ZonalStatisticsAsTable("flowPathsR", "VALUE", os.path.join(path,"D8FlowAcc"), os.path.join(path,"flowPathsFA"), "DATA", "MEDIAN")
    arcpy.JoinField_management("flowPaths", "OBJECTID", os.path.join(path,"flowPathsFA"), "Value", ["MEDIAN"])
    arcpy.AlterField_management("flowPaths", "MEDIAN", "FlowAcc", "FlowAcc")
    arcpy.JoinField_management("flowPaths", "FROM_ID", "watershedsPoly", "FROM_ID", ["RORUS"])
    arcpy.AddField_management("flowPaths", "LengthM", "DOUBLE")
    arcpy.CalculateGeometryAttributes_management("flowPaths", [["LengthM","LENGTH"]], "METERS")
    arcpy.Delete_management(os.path.join(path,"flowPathsFA"))
    arcpy.Delete_management(os.path.join(path,"flowPathsR"))

def joinUSP(): 
    arcpy.JoinField_management("flowPaths", "FROM_ID", os.path.join(path,"flowPathsUSP"), "FROM_ID", ["USP"])
    arcpy.JoinField_management("transects", "OBJECTID", os.path.join(path,"transectsUSP"), "transectID", ["Qd","S","W","USP"])
    arcpy.Delete_management(os.path.join(path,"flowPathsUSP"))
    arcpy.Delete_management(os.path.join(path,"transectsUSP"))
    arcpy.Delete_management(os.path.join(path,"transectPoints"))
    arcpy.Delete_management(os.path.join(path,"transectPoints2"))
    
# Select watersheds that are upstream of a selected watershed
def selectUpstream():
    i = 0
    j = 1
    FROMS = sorted(set([r[0] for r in arcpy.da.SearchCursor("watershedsPoly", "FROM_ID")]))
    while True:
        query = "TO_ID IN (" + str(FROMS)[1:-1] + ")"
        arcpy.SelectLayerByAttribute_management("watershedsPoly", "ADD_TO_SELECTION", query, None)
        FROMS = sorted(set([r[0] for r in arcpy.da.SearchCursor("watershedsPoly", "FROM_ID")]))
        j = int(arcpy.GetCount_management("watershedsPoly")[0])
        if j == i:
            break
        else:
            i = j
    
