from enum import Enum
from typing import List

class ActionCategory(str, Enum):
    SPATIAL_TRANSFORMATION = "Spatial Transformation"
    SELECTION_FILTERING = "Selection & Filtering"
    GROUPING_SEGMENTATION = "Grouping & Segmentation"
    MEASUREMENT_AGGREGATION = "Measurement & Aggregation"
    LOGICAL_TESTS = "Comparison & Logical Tests"
    COLOR_SYMBOL_MANIPULATION = "Color & Symbol Manipulation"
    ARITHMETIC_VECTOR_MATH = "Arithmetic & Vector Math"
    OBJECT_CREATION_DRAWING = "Object Creation & Drawing"
    SORTING_ORDERING = "Sorting & Ordering"
    MAPPING_TRANSFORMATION = "Mapping & Transformation"
    ATTRIBUTE_ACCESS = "Attribute Access & Extraction"
    PATTERN_DETECTION = "Structural Pattern Detection"

    @classmethod
    def list(cls) -> List[str]:
        return [c.value for c in cls]