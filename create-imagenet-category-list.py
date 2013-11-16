from imagenet_analysis import ImageNetData
import argparse
import json

parser = argparse.ArgumentParser()
parser.add_argument( '-i', '--inputsynsets', help='list of synsets', default='categories.synset')
parser.add_argument( '-d', '--datadir', help='ILSVRC devkit data directory', default='/home/dbv/bilder/ilsvrc2012/devkit-1.0/data/')
parser.add_argument( '-y', '--year', help='ILSVRC year', default='2012' )
parser.add_argument( '-o', '--outfn', help='output file name (JSON format)', default='categories.json' )
parser.add_argument( '-t', '--desctype', help='type of the category descriptions in the output', default='child', choices=['root', 'child'] )
parser.add_argument( '-s', '--shorten', help='shorten description', default=False, action='store_true' )
parser.add_argument( '--outputsynset', help='Output synset name rather than ILSVRC id', default=False, action='store_true' )

args = parser.parse_args()
synsetlistfn = args.inputsynsets
imnet = ImageNetData( args.datadir, ilsvrcyear=args.year)
outfn = args.outfn
shortendesc = args.shorten

with open(synsetlistfn,'r') as synsetlist:
  ids = {}

  for wnid in synsetlist:
    try:
      wnid = wnid.rstrip()
      idx = imnet.class_idx_from_wnid(wnid)
    except:
      print "# %s does not exists!" % (wnid)
      continue


    idxchilds = imnet.get_leafs(idx)
    rootdesc = imnet.description_from_class_idx( idx )
    print "# %s (%s)" % (wnid, rootdesc )
    for idxchild in idxchilds:
      childdesc = imnet.description_from_class_idx(idxchild)
      print "# -> %s" % ( childdesc )
      id = imnet.imagenet_id_from_class_idx ( idxchild )
      print "%d" % (id)

      
      if args.desctype == 'root':
        desc = rootdesc
      else:
        desc = childdesc

      if shortendesc:
        descitems = desc.split(',')
        desc = descitems[0].rstrip()

      if args.outputsynset:
        childwnid = imnet.wnid_from_class_idx ( idxchild )
        ids[childwnid] = desc
      else:
        ids[str(id)] = desc

with open (outfn, 'w') as outfile:
  json.dump ( ids, outfile, sort_keys=False, indent=4 )
