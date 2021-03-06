import sys
import os

sys.path.insert(0, os.path.join(os.getenv("HOME"),"python_packages/lib/python2.6/site-packages/"))

from scipy.io import loadmat
import numpy as np
import os
from glob import glob

from img_funcs import draw_bounding_boxes, grab_bounding_boxes
import xml.etree.ElementTree as ET

from joblib import Memory

memory = Memory("cache")
#import elementtree.ElementTree as ET

def pad_to(X, n):
    """Pad a 1-d array of size <= n with zeros to size n."""
    if X.ndim != 1:
        raise ValueError("Only 1-d arrays can be padded.")
    size = X.size
    if size == n:
        return X
    elif size < n:
        return np.hstack([X, np.zeros((n-size))])
    else:
        raise ValueError("Size of X must be smaller or equal to n.")

@memory.cache
def cached_bow(files):
    features = []
    file_names = []
    wnids = []
    counts = []

    for bow_file in files:
        print("loading %s"%bow_file)
        bow_structs = loadmat(bow_file, struct_as_record=False)['image_sbow']
        file_names.extend([str(x[0]._fieldnames) for x in bow_structs])
        bags_of_words = [pad_to(np.bincount(struct[0].sbow[0][0].word.ravel()), 1000) for struct in bow_structs]
        features.extend(bags_of_words)
        # if we where interested in the actual words:
        #words = [struct[0][1][0][0][0] for struct in bow_structs]
        # there is other stuff in the struct but I don't care at the moment:
        #x = [struct[0][1][0][0][1] for struct in bow_structs]
        #y = [struct[0][1][0][0][2] for struct in bow_structs]
        #scale = [struct[0][1][0][0][3] for struct in bow_structs]
        #norm = [struct[0][1][0][0][4] for struct in bow_structs]
        wnid = os.path.basename(bow_file).split(".")[0]
        wnids.append(wnid)
        counts.append(len(bags_of_words))
    features = np.array(features)
    return features, wnids, counts


class ImageNetData(object):
    """ ImageNetData needs path to meta.mat, path to images and path to annotations.
     The images are assumed to be in folders according to their synsets names

     Synsets are always handled using their index in the 'synsets' dict. This
     is their id-1 and is referred to as classidx.
     Images are handles using their image id, which is the number in the file name.
     These are non-concecutive and therefore called imgid.
     """
    def __init__(self, meta_path, image_path=None, annotation_path=None, bow_path=None, ilsvrcyear='2010'):
        self.image_path = image_path
        self.annotation_path = annotation_path
        self.meta_path = meta_path
        self.meta_data = loadmat(os.path.join(meta_path, "meta.mat"), struct_as_record=False)
        self.bow_path = bow_path
        self.ilsvrcyear = ilsvrcyear

        self.synsets = np.squeeze(self.meta_data['synsets'])

        #['ILSVRC2010_ID', 'WNID', 'words', 'gloss', 'num_children', 'children', 'wordnet_height', 'num_train_images']
        if self.ilsvrcyear == '2012':
          self.ids = np.squeeze(np.array([x.ILSVRC2012_ID for x in self.synsets]))
        elif self.ilsvrcyear == '2011':
          self.ids = np.squeeze(np.array([x.ILSVRC2011_ID for x in self.synsets]))
        else:
          self.ids = np.squeeze(np.array([x.ILSVRC2010_ID for x in self.synsets]))

        self.idx = {}
        for index, id in np.ndenumerate(self.ids):
          self.idx[id] = index[0]

        self.wnids = np.squeeze(np.array([x.WNID for x in self.synsets]))
        self.word = np.squeeze(np.array([x.words for x in self.synsets]))
        self.num_children = np.squeeze(np.array([x.num_children for x in self.synsets]))
        self.children_ids = [(np.squeeze(x.children).astype(np.int)) for x in self.synsets]

    def wnid_from_class_idx ( self, classidx ):
        return self.wnids[classidx]

    def description_from_class_idx ( self, classidx ):
        return self.word[classidx]

    def imagenet_id_from_class_idx ( self, classidx ):
        return self.ids[ classidx ]

    def img_path_from_imgid(self, classidx, imgid):
        wnid = self.wnids[classidx]
        return os.path.join(self.image_path, wnid, wnid+'_'+imgid+".JPEG")

    def class_idx_from_string(self, search_string):
        """Get class index from string in class name."""
        indices = np.where([search_string in x[2][0] for x in self.synsets])[0]
        return indices

    def get_leafs(self, classidx):
        """Traverse tree to the leafes. Takes classidx, returns
        list of all leafs corresponding to the class."""

        if self.num_children[classidx] == 0:
          return [ classidx ]

        rchildren = []
        # minus one converts ids into indices in our arrays
        children_ids = self.children_ids[classidx]

        for child_id in np.nditer(children_ids):
          rchildren.extend( self.get_leafs( self.idx[ int(child_id) ] ) )

        return rchildren

    def get_bndbox(self, classidx, imageid):
        """Get bouning box coordinates for image with id ``imageid``
        in synset given by ``classidx``."""

        wnid = self.wnids[classidx]
        annotation_file = os.path.join(self.annotation_path, str(wnid), str(wnid) + "_" + str(imageid) + ".xml")
        xmltree = ET.parse(annotation_file)
        objects = xmltree.findall("object")
        result = []
        for object_iter in objects:
            bndbox = object_iter.find("bndbox")
            result.append([int(it.text) for it in bndbox])
        #[xmin, ymin, xmax, ymax] = [it.text for it in bndbox]
        return result

    def get_image_ids(self, classidx):
        wnid = self.wnids[classidx]
        
        files = glob(os.path.join(self.image_path,wnid,wnid+"*"))
        filenames = [os.path.basename(f)[:-5] for f in files]
        numbers = map(lambda f: f.split("_")[1], filenames)
        return numbers

    def bounding_box_images(self, classidx):
        """Get list of cut out bounding boxes
        for a given classidx."""

        if not os.path.exists("output/bounding_box"):
            os.mkdir("output/bounding_box")
        wnid = self.wnids[classidx]
        if not os.path.exists(os.path.join("output/bounding_box", wnid)):
            os.mkdir(os.path.join("output/bounding_box", wnid))

        image_ids = self.get_image_ids(classidx)
        bbfiles = []
        for imgid in image_ids:
            try:
                bounding_boxes = self.get_bndbox(classidx, imgid)
            except IOError:
                #no bounding box
                #print("no xml found")
                continue
            bbfiles.append(imgid)
            img_path = self.img_path_from_imgid(classidx, imgid)
            out_path = str(os.path.join("output/bounding_box", wnid, wnid+'_'+imgid+".png"))
            draw_bounding_boxes(img_path, bounding_boxes, out_path)
            #if len(bbfiles)>2:
                #break
        print("annotated files: %d"%len(bbfiles))

    def class_idx_from_wnid(self, wnid):
        """Get class index in ``self.synset`` from synset id"""
        result = np.where(self.wnids==wnid)
        if len(result[0]) == 0:
            raise ValueError("Invalid wnid.")
        return result[0][0]

    def all_bounding_boxes(self, classidx):
        image_ids = self.get_image_ids(classidx)
        all_bbs = []
        for imgid in image_ids:
            try:
                img_bbs = self.get_bndbox(classidx, imgid)
            except IOError:
                #no bounding box
                #print("no xml found")
                continue
            f = self.img_path_from_imgid(classidx, imgid)
            all_bbs.extend(grab_bounding_boxes(f, img_bbs))
        return all_bbs;

    def load_val_labels(self):
        return np.loadtxt(os.path.join(self.meta_path, "ILSVRC%s_validation_ground_truth.txt" % (self.ilsvrcyear)))

    def load_bow(self, dataset="train"):
        """Get bow representation of dataset ``dataset``.
        Legal values are ``train``, ``val`` and ``test``.

        Returns
        -------
        features : numpy array, shape [n_samples, n_features],
            containing bow representation of all images in given dataset

        labels : numpy array, shape [n_samples],
            containing classidx for image labels. (Not available for ``test``)
        """
        if not self.bow_path:
            raise ValueError("You have to specify the path to" 
                "the bow features in ``bow_path`` to be able"
                "to load them")

        files = glob(os.path.join(self.bow_path, dataset, "*.sbow.mat"))

        if len(files) == 0:
            raise ValueError("Could not find any bow files.")

        features, wnids, counts = cached_bow(files)

        if dataset == "train":
            labels_nested = [[self.class_idx_from_wnid(wnid)] * count for wnid, count in zip(wnids, counts)]
            labels = np.array([x for l in labels_nested for x in l])
        elif dataset == "val":
            labels = self.load_val_labels()
        elif dataset == "test":
            labels = None
        else:
            raise ValueError("Unknow dataset %s"%dataset)

        return features, labels


def main():
    # ImageNetData needs path to meta.mat, path to images and path to annotations.
    # The images are assumed to be in folders according to their synsets names
    #imnet = ImageNetData("ILSVRC2011_devkit-2.0/data", "unpacked", "annotation")
    imnet = ImageNetData("/nfs3group/chlgrp/datasets/ILSVRC2010/devkit-1.0/data",
            bow_path="/nfs3group/chlgrp/datasets/ILSVRC2010")

    features, labels = imnet.load_bow()
    features_val, labels_val = imnet.load_bow('val')

    from IPython.core.debugger import Tracer
    tracer = Tracer(colors="LightBG")
    tracer()
        
        

if __name__ == "__main__":
    main()
