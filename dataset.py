"""
References:
    https://gist.github.com/kyamagu/0aa8c06501bd8a5816640639d4d33a17
    https://github.com/sgrvinod/a-PyTorch-Tutorial-to-Object-Detection/tree/43fd8be9e82b351619a467373d211ee5bf73cef8
"""
from tools.load_symbol_cluster import load_symbol_cluster, UNCLEAR_CLUSTER_ID
import os
import torch
import json
import logging
import re
from PIL import Image
from torch.utils.data import Dataset


logger = logging.getLogger()


class AdsDataset(Dataset):
    """Load the images and annotation files into a PyTorch dataset
    """
    JSON_RESOURCES = {
        "qa": "QA_Combined_Action_Reason",
        "sentiments": "Sentiments",
        "slogans": "Slogans",
        "strategies": "Strategies",
        "symbols": "Symbols",
        "topics": "Topics",
    }
    TEXT_RESOURCES = {
        "sentiments_list": ("Sentiments_List.txt", "latin_1"),
        "topics_list": ("Topics_List.txt", "utf-16le"),
        "strategies_list": ("Strategies_List.txt", "latin_1")
    }

    def __init__(self, descriptor="sentiments", root="data", transforms=None):
        """Construct a PyTorch Dataset object

        Args:
            descriptor (str, optional): selected descriptor. Defaults to "sentiments".
            root (str, optional): root directory containing the images and annotations. Defaults to "data".
            transforms (None, optional): a function to transform the item in dataset. Defaults to None.
        """
        self.root = root
        self.transforms = transforms
        self._load(descriptor)

    def __getitem__(self, index: int):
        """Retrieve the image, bounding boxes, and labels of the item
        at index of the datset

        Args:
            index (int): index number

        Returns:
            (image, boxes, labels, difficulties): a tuple of image, bounding boxes, labels, and difficulties
        """
        # convert index to tensor
        image_id = torch.tensor([index])
        key = self.image_path[index]
        # read the image
        filename = os.path.join(
            self.root, "{}".format(key))
        image = Image.open(filename, mode='r').convert('RGB')
        image = image.resize((501, 501))
        # retrieve the label and encode it
        labels = []
        word_to_id, _ = load_symbol_cluster()
        for data in self.symbols[key]:
            symbols = [s.strip()
                       for s in data[4].lower().split('/') if len(s.strip()) > 0]
            symbols = [word_to_id[s] for s in symbols if s in word_to_id]
            most_common_cluster_id = max(symbols, key=symbols.count) if len(
                symbols) else UNCLEAR_CLUSTER_ID
            labels.append(most_common_cluster_id)
        # retrieve the bounding boxes
        boxes = []
        for data in self.symbols[key]:
            xmin = min(data[0], data[2])
            ymin = min(data[1], data[3])
            xmax = max(data[0], data[2])
            ymax = max(data[1], data[3])
            boxes.append([xmin, ymin, xmax, ymax])
        # convert bounding boxes and labels to tensors
        labels = torch.as_tensor(labels, dtype=torch.int64)  # (n_objects)
        boxes = torch.as_tensor(boxes, dtype=torch.float32)  # (n_objects, 4)
        # calculate the area using bounding boxes (width * height)
        area = (boxes[:, 3] - boxes[:, 1]) * (boxes[:, 2] - boxes[:, 0])
        # suppose all instances are not crowd
        iscrowd = torch.zeros((labels.size(0),), dtype=torch.int64)
        # create target
        target = {}
        target["boxes"] = boxes
        target["labels"] = labels
        target["image_id"] = image_id
        target["area"] = area
        target["iscrowd"] = iscrowd
        # transforms image and target
        if self.transforms is not None:
            image, target = self.transforms(image, target)
        return image, target

    def __len__(self) -> int:
        """Return the size of the dataset

        Returns:
            int: number of images in the dataset
        """
        return len(self.image_path)

    def _load(self, descriptor: str) -> None:
        """Load the annotation resources

        Args:
            descriptor (str): selected descriptor from one of the annotations
        """
        # Load the field's data
        for field in self.JSON_RESOURCES:
            filename = os.path.join(
                self.root, "annotations/{}.json".format(self.JSON_RESOURCES[field]))
            logger.debug("Loading {}".format(filename))
            with open(filename, "r") as f:
                setattr(self, field, json.load(f))
            if field == descriptor:
                with open(filename, "r") as f:
                    setattr(self, 'descriptor', json.load(f))

        # Find the common keys between the descriptor and symbols
        self.image_path = self._find_common_keys(
            list(self.descriptor.keys()), list(self.symbols.keys()))

        # Load the sentiments and topics key-value pairs
        for field in self.TEXT_RESOURCES:
            self._load_resources(field)
        # Hack.
        self.topics_list["39"] = {"name": "Unclear", "description": ""}

    def _load_resources(self, field: str) -> None:
        """Load the text resources

        Args:
            field (str): the field in the TEXT_RESOURCES
        """
        filename, encoding = self.TEXT_RESOURCES[field]
        records = {}
        logger.debug("Loading {}".format(filename))
        with open(os.path.join(self.root, "annotations", filename), "r", encoding=encoding) as f:
            for line in f:
                line = line.encode("ascii", "ignore").decode("utf-8").strip()
                match = re.match(r'^(?P<id>\d+)\.?\D+'
                                 r'"(?P<description>[^"]+)"\W+'
                                 r'\(ABBREVIATION:\s+"(?P<abbr>[^"]+)"\).*$', line)
                if match:
                    records[match.group("id")] = {
                        "name": match.group("abbr"),
                        "description": match.group("description"),
                    }
        setattr(self, field, records)

    def _find_common_keys(self, key_one, key_two):
        """Find the intersection of the two lists of keys

        Args:
            key_one (List[str]): a list of image path
            key_two (List[str]): a list of image path

        Returns:
            List[str]: a list of image path
        """
        unique_keys = []
        for i in range(len(key_two)):
            key = key_two[i]
            if key in key_one:
                unique_keys.append(key)
        return unique_keys