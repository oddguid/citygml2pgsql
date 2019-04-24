#!/usr/bin/python
# coding: utf-8
"""Convert CityGML buildings to PostreSQL statements for insersion in table

USAGE
    citygml2pgsql -l file1.xml [file2.xml ...] 
    citygml2pgsql file1.xml [file2.xml ...] <lod> srid geometry_column building_id_column table_name

    <lod> can be 0, 1, 2, 3
    srid

OPTIONS
    -h, --help display this message

    -l, --list list geometry type en srs found in file

"""

import os
import sys
import re
from lxml import etree


def gmlLinearRing2wkt(ring, dim):
    dim = int(ring.get("srsDimension")) if ring.get("srsDimension") else dim
    dim = int(ring[0].get("srsDimension")) if ring[0].get("srsDimension") else dim
    dim = dim if dim else 3
    raw_coord = ring[0].text.split()
    coord = [raw_coord[i:i+dim] for i in range(0, len(raw_coord), dim)]
    if coord[0] != coord[-1]:
        coord.append(coord[0]) # close ring if not closed
    if len(coord) < 4:
        sys.stderr.write( 'degenerated LinearRing gml:id="'+\
                ring.get("{http://www.opengis.net/gml}id")+'"\n')
        return None
    assert len(coord) >= 4
    return "("+",".join([" ".join(c) for c in coord])+")"

def gmlPolygon2wkt(poly, dim):
    dim = int(poly.get("srsDimension")) if poly.get("srsDimension") else dim
    rings = filter(None, [gmlLinearRing2wkt(ring, dim) \
            for ring in poly.iter("{http://www.opengis.net/gml}LinearRing") ])
    if not rings:
        sys.stderr.write( 'degenerated Polygon gml:id="'+\
                poly.get("{http://www.opengis.net/gml}id")+'"\n')
        return None
    return "("+",".join(rings)+")"

def findNamespaceFor(elmentName, root):
    for e in root.iter():
        if e.tag is etree.Comment:
            continue
        m = re.match(r"(.*)"+elmentName, e.tag) if e.tag else None
        if m:
            return m.groups()[0]
    return None

def fullName(elmentName, root):
    namespace = findNamespaceFor(elmentName, root)
    return namespace+elmentName if namespace else None

def buildingGeomTypes(root, lods=range(3)):
    types = set()
    name = fullName('Building', root)
    if not name:
        return types
    for building in root.iter(name):
        for geom_type in ['Solid', 'MultiSurface', 'CompositeSurface']:
            for lod in lods :
                type_ = fullName('lod'+str(lod)+geom_type, building)
                if type_:
                   types.add(type_)
    return types


def citygml2pgsql(filename, table_name, srid, lod, geometry_column="geom", building_id_column="building_id"):
    if not os.path.exists(filename):
        raise RuntimeError("error: cannot find "+filename)

    root = etree.parse(filename)

    #generate a multipolygon surface per building

    geom_types = buildingGeomTypes(root, [lod])

    for building in root.iter(fullName("Building", root)):
        building_id = building.attrib["{http://www.opengis.net/gml}id"]
        building_polys = []
        for geom_type in geom_types:
            for geom in building.iter(geom_type):
                dim = int(geom.get("srsDimension")) if geom.get("srsDimension") else None
                polys = filter(None, [gmlPolygon2wkt(poly, dim) \
                            for poly in geom.iter(fullName("Polygon", building))])
                building_polys = building_polys + list(polys)
        if len(building_polys) != 0:
            print("INSERT INTO "+table_name+"("+geometry_column + "," + building_id_column + ") VALUES ("\
                  "'SRID="+str(srid)+\
                    "; MULTIPOLYGON("+",".join(building_polys)+\
                    ")'::geometry, '" + str(building_id) + "' );")
        else:
            sys.stderr.write( 'degenerated '+geom+' gml:id="'+\
                    geom.get("{http://www.opengis.net/gml}id")+'"\n')

if __name__ == '__main__':
    
    if len(sys.argv) >= 2 and sys.argv[1] in ["-h","--help"]:
        help(sys.modules[__name__])
        exit(0)

    if len(sys.argv) >= 3 and sys.argv[1] in ["-l", "--list"]:
        for filename in sys.argv[2:]:
            srs = set()
            print("In", filename)
            with open(filename) as xml:
                for line in xml:
                    m = re.match(r'.*srsName="([^"]+)"', line)
                    if m:
                        srs.add(m.groups()[0])
            for srid in srs:
                print("    found reference to", srid)
            root = etree.parse(filename)
            for geom in buildingGeomTypes(root):
                print("    found geometries", re.sub('.*}', '', geom))
        exit(0)

    if len(sys.argv) < 5:
        print("error: wrong number of arguments (try "+sys.argv[0]+" --help)")
        exit(1)

    table_name = sys.argv[-1]
    building_id_column = sys.argv[-2]
    geometry_column = sys.argv[-3]
    srid = int(sys.argv[-4])
    lod = int(sys.argv[-5])
    for filename in sys.argv[1:-5]:
        sys.stderr.write("converting "+filename+"\n")
        citygml2pgsql(filename, table_name, srid, lod, geometry_column, building_id_column)

