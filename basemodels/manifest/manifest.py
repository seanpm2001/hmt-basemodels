import uuid
import requests
from requests.exceptions import RequestException
from typing import Callable, Any
from schematics.models import Model, ValidationError
from schematics.exceptions import BaseError
from schematics.types import (
    StringType,
    DecimalType,
    IntType,
    DictType,
    ListType,
    URLType,
    FloatType,
    UUIDType,
    ModelType,
    BooleanType,
    UnionType,
)

from basemodels.manifest.data.groundtruth import validate_groundtruth_entry
from basemodels.manifest.data.taskdata import validate_taskdata_entry
from basemodels.manifest.data.requester_question_example import validate_requester_example_image
from basemodels.manifest.data.requester_restricted_answer_set import validate_requester_restricted_answer_set_uris
from basemodels.manifest.restricted_audience import RestrictedAudience
from basemodels.constants import JOB_TYPES_FOR_CONTENT_TYPE_VALIDATION

BASE_JOB_TYPES = [
    "image_label_binary",
    "image_label_multiple_choice",
    "text_free_entry",
    "text_multiple_choice_one_option",
    "text_multiple_choice_multiple_options",
    "image_label_area_adjust",
    "image_label_area_select",
    "image_label_single_polygon",
    "image_label_multiple_polygons",
    "image_label_semantic_segmentation_one_option",
    "image_label_semantic_segmentation_multiple_options",
    "image_label_text",
]


def validate_request_type(self, data, value):
    """
    validate request types for all types of challenges
    multi_challenge should always have multi_challenge_manifests
    """
    # validation runs before other params, so need to handle missing case
    if not data.get("request_type"):
        raise ValidationError("request_type missing")

    if data.get("request_type") == "multi_challenge":
        if not data.get("multi_challenge_manifests"):
            raise ValidationError("multi_challenge requires multi_challenge_manifests.")
    elif data.get("request_type") in ["image_label_multiple_choice", "image_label_area_select"]:
        if data.get("multiple_choice_min_choices", 1) > data.get("multiple_choice_max_choices", 1):
            raise ValidationError("multiple_choice_min_choices cannot be greater than multiple_choice_max_choices")

    return value


class Webhook(Model):
    """Model for webhook configuration"""

    webhook_id = UUIDType(required=True)
    chunk_completed = ListType(StringType(), required=False)
    job_completed = ListType(StringType(), required=False)

    # States that might be interesting later
    # job_skipped = ListType(StringType(), required=False)
    # job_inserted = ListType(StringType(), required=False)
    # job_activated = ListType(StringType(), required=False)


class TaskData(Model):
    """objects within taskdata list in Manifest"""

    task_key = UUIDType(required=True)
    datapoint_uri = URLType()
    datapoint_hash = StringType(required=True, min_length=10)
    datapoint_text = DictType(StringType)

    def validate_datapoint_uri(self, data, value):
        """
        Validate datapoint_uri.

        Raise error if no datapoint_text and no value for URI or if length of URI less than 10.
        """
        if not value and not data.get("datapoint_text"):
            raise ValidationError("datapoint_uri is missing.")
        if value and len(value) < 10 and not data.get("datapoint_text"):
            raise ValidationError("datapoint_uri length is less than 10")
        return value


class RequestConfig(Model):
    """definition of the request_config object in manifest"""

    version = IntType(default=0)
    shape_type = StringType(choices=["point", "bounding_box", "polygon"])
    min_points = IntType()
    max_points = IntType()
    min_shapes_per_image = IntType()
    max_shapes_per_image = IntType()
    restrict_to_coords = BooleanType()
    minimum_selection_area_per_shape = IntType()
    multiple_choice_max_choices = IntType(default=1)
    multiple_choice_min_choices = IntType(default=1)
    overlap_threshold = FloatType(required=False)
    answer_type = StringType(choices=["int", "float", "str"], default="str")
    max_value = FloatType()
    min_value = FloatType()
    max_length = IntType()
    min_length = IntType()
    sig_figs = IntType()
    keep_answers_order = BooleanType(default=False)


class InternalConfig(Model):
    """discarded from incoming manifests"""

    exchange = DictType(UnionType([StringType, IntType, FloatType]))
    reco = DictType(UnionType([StringType, IntType, FloatType]))
    repo = DictType(UnionType([StringType, IntType, FloatType]))
    other = DictType(UnionType([StringType, IntType, FloatType]))
    # Accept one layer of nested
    mitl = DictType(
        UnionType(
            [
                StringType,
                IntType,
                FloatType,
                DictType(UnionType([StringType, IntType, FloatType])),
            ]
        )
    )


class NestedManifest(Model):
    """The nested manifest description for multi_challenge jobs"""

    job_id = UUIDType(default=uuid.uuid4)

    requester_restricted_answer_set = DictType(DictType(StringType))

    def validate_requester_restricted_answer_set(self, data, value):
        """image_label_area_select should always have a single RAS set"""

        # validation runs before other params, so need to handle missing case
        if not data.get("request_type"):
            raise ValidationError("request_type missing")

        if data["request_type"] == "image_label_area_select":
            if not value or len(value.keys()) == 0:
                value = {"label": {}}
                data["requester_restricted_answer_set"] = value

        if data["request_type"] == "image_label_multiple_choice":
            if not value or len(value.keys()) <= 1:
                raise ValidationError(
                    "image_label_multiple_choice needs at least 2+ options in requester_restricted_answer_set"
                )
            elif len(value.keys()) > 4:
                raise ValidationError(
                    "image_label_multiple_choice can not handle more than 4 options requester_restricted_answer_set"
                )
        return value

    requester_description = StringType()
    requester_max_repeats = IntType(default=100)
    requester_min_repeats = IntType(default=1)
    requester_question = DictType(StringType)

    requester_question_example = UnionType((URLType, ListType), field=URLType)

    requester_example_extra_fields = UnionType([DictType(StringType), ListType(DictType(StringType))], required=False)

    def validate_requester_question_example(self, data, value):
        # validation runs before other params, so need to handle missing case
        if not data.get("request_type"):
            raise ValidationError("request_type missing")

        # based on https://github.com/hCaptcha/hmt-basemodels/issues/27#issuecomment-590706643
        supports_lists = ["image_label_area_select", "image_label_binary"]

        if isinstance(value, list) and not data["request_type"] in supports_lists:
            raise ValidationError("Lists are not allowed in this challenge type")
        return value

    unsafe_content = BooleanType(default=False)
    requester_accuracy_target = FloatType(default=0.1)
    request_type = StringType(required=True, choices=BASE_JOB_TYPES)
    validate_request_type = validate_request_type

    request_config = ModelType(RequestConfig, required=False)

    # Groundtruth data is stored as a URL or optionally as an inlined json-serialized stringtype
    groundtruth_uri = URLType(required=False)
    groundtruth = StringType(required=False)

    def validate_groundtruth(self, data, value):
        if data.get("groundtruth_uri") and data.get("groundtruth"):
            raise ValidationError("Specify only groundtruth_uri or groundtruth, not both.")
        return value

    # Configuration id -- XXX LEGACY
    confcalc_configuration_id = StringType(required=False)

    webhook = ModelType(Webhook)


class Manifest(Model):
    """The manifest description."""

    job_mode = StringType(required=True, choices=["batch", "online", "instant_delivery"])
    job_api_key = UUIDType(default=uuid.uuid4)
    job_id = UUIDType(default=uuid.uuid4)
    job_total_tasks = IntType(required=True)
    network = StringType(required=False)
    only_sign_results = BooleanType(
        default=False,
    )
    public_results = BooleanType(
        default=False,
    )

    requester_restricted_answer_set = DictType(DictType(StringType))

    def validate_requester_restricted_answer_set(self, data, value):
        """image_label_area_select should always have a single RAS set"""
        # validation runs before other params, so need to handle missing case
        if not data.get("request_type"):
            raise ValidationError("request_type missing")

        if data["request_type"] == "image_label_area_select":
            if not value or len(value.keys()) == 0:
                value = {"label": {}}
                data["requester_restricted_answer_set"] = value

        if data["request_type"] == "image_label_multiple_choice":
            if not value or len(value.keys()) <= 1:
                raise ValidationError(
                    "image_label_multiple_choice needs at least 2+ options in requester_restricted_answer_set"
                )
            elif len(value.keys()) > 4:
                raise ValidationError(
                    "image_label_multiple_choice can not handle more than 4 options requester_restricted_answer_set"
                )
        return value

    requester_description = StringType()
    requester_max_repeats = IntType(default=100)
    requester_min_repeats = IntType(default=1)
    requester_question = DictType(StringType)

    requester_question_example = UnionType((URLType, ListType), field=URLType)

    requester_example_extra_fields = UnionType([DictType(StringType), ListType(DictType(StringType))])

    def validate_requester_question_example(self, data, value):
        # validation runs before other params, so need to handle missing case
        if not data.get("request_type"):
            raise ValidationError("request_type missing")

        # based on https://github.com/hCaptcha/hmt-basemodels/issues/27#issuecomment-590706643
        supports_lists = ["image_label_area_select", "image_label_binary"]

        if isinstance(value, list) and not data["request_type"] in supports_lists:
            raise ValidationError("Lists are not allowed in this challenge type")
        return value

    unsafe_content = BooleanType(default=False)
    task_bid_price = DecimalType(required=True)
    oracle_stake = DecimalType(required=True)
    expiration_date = IntType()
    requester_accuracy_target = FloatType(default=0.1)
    manifest_smart_bounty_addr = StringType()
    hmtoken_addr = StringType()
    minimum_trust_server = FloatType(default=0.1)
    minimum_trust_client = FloatType(default=0.1)
    recording_oracle_addr = StringType(required=True)
    reputation_oracle_addr = StringType(required=True)
    reputation_agent_addr = StringType(required=True)
    requester_pgp_public_key = StringType()
    ro_uri = StringType()
    repo_uri = StringType()

    batch_result_delivery_webhook = URLType()
    online_result_delivery_webhook = URLType()
    instant_result_delivery_webhook = URLType()

    multi_challenge_manifests = ListType(ModelType(NestedManifest), required=False)

    request_type = StringType(required=True, choices=BASE_JOB_TYPES + ["multi_challenge"])
    validate_request_type = validate_request_type

    request_config = ModelType(RequestConfig, required=False)

    # If taskdata is directly provided
    taskdata = ListType(ModelType(TaskData))

    # If taskdata is separately stored
    taskdata_uri = URLType()

    # Groundtruth data is stored as a URL or optionally as an inlined json-serialized stringtype
    groundtruth_uri = URLType(required=False)
    groundtruth = StringType(required=False)

    rejected_uri = URLType(required=False)
    rejected_count = IntType(default=0, required=False)

    def validate_groundtruth(self, data, value):
        if data.get("groundtruth_uri") and data.get("groundtruth"):
            raise ValidationError("Specify only groundtruth_uri or groundtruth, not both.")
        return value

    # internal config options for param tests etc.
    internal_config = ModelType(InternalConfig, required=False)

    # Configuration id -- XXX LEGACY
    confcalc_configuration_id = StringType(required=False)

    restricted_audience = ModelType(RestrictedAudience, required=True, default={})

    is_verification = BooleanType(default=False, required=False)

    def validate_taskdata_uri(self, data, value):
        if data.get("taskdata") and len(data.get("taskdata")) > 0 and data.get("taskdata_uri"):
            raise ValidationError(
                "Specify only one of taskdata {} or taskdata_uri {}".format(
                    data.get("taskdata"), data.get("taskdata_uri")
                )
            )
        return value

    validate_taskdata = validate_taskdata_uri

    webhook = ModelType(Webhook)


def traverse_json_entries(data: Any, callback: Callable, validate_image_content_type: bool) -> int:
    """
    Traverse json and execute callback for each top-level entry

    Could later be optimized by accepting json uri instead of the full object
    and using streaming request/parse APIs to exit early on validation error

    Returns entries count if succeeded
    """

    entries_count = 0

    if isinstance(data, dict):
        for k, v in data.items():
            entries_count += 1
            callback(k, v, validate_image_content_type)
            validate_image_content_type = False

    elif isinstance(data, list):
        for v in data:
            entries_count += 1
            callback(None, v, validate_image_content_type)
            validate_image_content_type = False

    return entries_count


def validate_manifest_uris(manifest: dict):
    """Fetch & validate manifest's remote objects"""

    request_type = manifest.get("request_type", "")
    entry_validators = {
        "groundtruth_uri": lambda k, v, validate: validate_groundtruth_entry(k, v, request_type, validate),
        "taskdata_uri": lambda _, v, validate: validate_taskdata_entry(v, validate),
    }

    for uri_key, validate_entry in entry_validators.items():
        validate_image_content_type = request_type in JOB_TYPES_FOR_CONTENT_TYPE_VALIDATION
        uri = manifest.get(uri_key)

        if uri is None:
            continue

        try:
            response = requests.get(uri)
            response.raise_for_status()

            entries_count = traverse_json_entries(response.json(), validate_entry, validate_image_content_type)
        except (BaseError, RequestException) as e:
            raise ValidationError(f"{uri_key} validation failed: {e}") from e

        if entries_count == 0:
            raise ValidationError(f"fetched {uri_key} is empty")


def validate_manifest_example_images(manifest: dict):
    """Fetch and validate the example resources."""
    question_example = manifest.get("requester_question_example")
    req_res_answer_set = manifest.get("requester_restricted_answer_set", {})
    if question_example:
        # some jobs might not have requester_question_example
        validate_requester_example_image(question_example)
    if req_res_answer_set:
        validate_requester_restricted_answer_set_uris(req_res_answer_set)
