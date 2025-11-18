import uuid
import json
import logging
import requests
from urllib.parse import urlencode
from .MercariItemPydantic import Item as MercariItemFull, ItemAuction
from .DpopUtils import generate_DPOP

# Set up logger for validation errors
logger = logging.getLogger(__name__)

rootURL = "https://api.mercari.jp/"
rootProductURL = "https://jp.mercari.com/item/"
searchURL = "{}v2/entities:search".format(rootURL)
itemInfoURL = "{}items/get".format(rootURL) # idk why not v2


class MercariSearchStatus:
    DEFAULT = "STATUS_DEFAULT"
    ON_SALE = "STATUS_ON_SALE"
    SOLD_OUT = "STATUS_SOLD_OUT"

class MercariSort:
    SORT_DEFAULT = 'SORT_DEFAULT'
    SORT_CREATED_TIME = 'SORT_CREATED_TIME'
    SORT_NUM_LIKES = 'SORT_NUM_LIKES'
    SORT_SCORE = 'SORT_SCORE'
    SORT_PRICE = 'SORT_PRICE'

class MercariOrder:
    ORDER_DESC = 'ORDER_DESC'
    ORDER_ASC = 'ORDER_ASC'

class MercariItemStatus:
    ITEM_STATUS_UNSPECIFIED = 'ITEM_STATUS_UNSPECIFIED'
    ITEM_STATUS_ON_SALE = 'ITEM_STATUS_ON_SALE'
    ITEM_STATUS_TRADING = 'ITEM_STATUS_TRADING'
    ITEM_STATUS_SOLD_OUT = 'ITEM_STATUS_SOLD_OUT'
    ITEM_STATUS_STOP = 'ITEM_STATUS_STOP'
    ITEM_STATUS_CANCEL = 'ITEM_STATUS_CANCEL'
    ITEM_STATUS_ADMIN_CANCEL = 'ITEM_STATUS_ADMIN_CANCEL'

class Item:
    def __init__(self, *args, **kwargs):
        self.id = kwargs['id']
        self.productURL = "{}{}".format(rootProductURL, kwargs['id'])
        self.imageURL = kwargs['thumbnails'][0]
        self.productName = kwargs['name']
        self.price = kwargs['price']
        self.status = kwargs['status']
        self.soldOut = kwargs['status'] != MercariItemStatus.ITEM_STATUS_SOLD_OUT
        self.created = kwargs['created']
        self.updated = kwargs['updated']
        # this is optional, only present if the item is an auction
        if "auction" in kwargs and kwargs["auction"] is not None:
            self.auction = ItemAuction(**kwargs['auction'])
        else:
            self.auction = None

    @staticmethod
    def fromApiResp(apiResp):
        return Item(
            **apiResp
        )

# because requests is doing some dumb bullshit and using capital booleans
# we'll force lowercase booleans to fix this dumb shit
def convert_booleans(obj):
    if isinstance(obj, bool):
        return str(obj).lower()
    elif isinstance(obj, dict):
        # Recursively process each key-value pair in the dictionary
        return {k: convert_booleans(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        # Recursively process each item in the list
        return [convert_booleans(item) for item in obj]
    else:
        return obj
    
# used for the search endpoint
# returns [] if resp has no items on it
# returns [Item's] otherwise
def parse(resp):
    if(len(resp["items"]) == 0):
        return [], False, None

    respItems = resp["items"]
    nextPageToken = resp["meta"]["nextPageToken"]
    return [Item.fromApiResp(item) for item in respItems], bool(nextPageToken), nextPageToken

# used for the itemInfo endpoint
def parseItemInfo(resp):
    """Parse item info using Pydantic for automatic validation."""
    from pydantic import ValidationError

    try:
        # Handle nested auction_info field if present
        data = resp['data'].copy()
        if 'auction_info' in data and data['auction_info'] is not None:
            data['auction'] = data.pop('auction_info')

        return MercariItemFull(**data)
    except ValidationError as e:
        # Extract field names from validation errors for better diagnostics
        error_fields = []
        for error in e.errors():
            # error['loc'] is a tuple like ('comments', 0) for comments.0
            field_path = '.'.join(str(x) for x in error['loc'])
            error_type = error['type']
            error_fields.append(f"{field_path} ({error_type})")

        # Log validation errors with field names
        logger.error(f"Failed to parse item info: {len(e.errors())} validation error(s)")
        logger.error(f"  Failed fields: {', '.join(error_fields)}")

        # Log specific field structures that commonly cause issues
        if 'comments' in resp['data']:
            comments = resp['data']['comments']
            logger.debug(f"Comments field type: {type(comments)}, length: {len(comments) if isinstance(comments, list) else 'N/A'}")
            if isinstance(comments, list) and len(comments) > 0:
                logger.debug(f"First comment structure: {type(comments[0])} - {comments[0]}")

        # Log auction field if that's causing issues
        if 'auction_info' in resp['data'] or 'auction' in resp['data']:
            auction_data = resp['data'].get('auction_info') or resp['data'].get('auction')
            if auction_data:
                logger.debug(f"Auction data: {auction_data}")

        # Only log full raw data in debug mode to avoid spam
        logger.debug(f"Full raw data keys: {resp['data'].keys()}")
        raise
    except KeyError as e:
        logger.error(f"Missing required field in response: {e}")
        logger.debug(f"Response structure: {resp.keys()}")
        raise

def fetch(url, data, parser, method="POST"):
    # For GET requests, construct the full URL with query parameters
    # This is critical for DPOP authentication to work correctly
    if method == "GET":
        # Convert data to query string and append to URL
        query_params = convert_booleans(data)
        query_string = urlencode(query_params)
        dpop_url = f"{url}?{query_string}"
    else:
        dpop_url = url

    # Generate DPOP token with the complete URL (including query params for GET)
    # Use random UUID instead of hardcoded string to avoid tracking
    DPOP = generate_DPOP(
        uuid=str(uuid.uuid4()),
        method=method,
        url=dpop_url,
    )

    headers = {
        'DPOP': DPOP,
        'X-Platform': 'web',  # mercari requires this header
        'Accept': '*/*',
        'Accept-Encoding': 'deflate, gzip',
        'Content-Type': 'application/json; charset=utf-8',
        # Use realistic browser User-Agent to avoid bot detection
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    }

    serializedData = json.dumps(data, ensure_ascii=False).encode('utf-8')

    try:
        if method == "POST":
            r = requests.post(url, headers=headers, data=serializedData)
        else:
            r = requests.get(url, headers=headers, params=convert_booleans(data))

        r.raise_for_status()

    except requests.exceptions.HTTPError as e:
        # Log authentication errors specifically
        if r.status_code == 401:
            logger.warning(f"Authentication failed (401) for URL: {dpop_url}")
            logger.debug(f"Request headers (DPOP omitted): X-Platform={headers['X-Platform']}, User-Agent={headers['User-Agent']}")
            logger.debug(f"Response: {r.text[:200] if r.text else 'empty'}")
        raise

    return parser(r.json())

# not sure if the v1 prefix ever changes, but from quick testing, doesn't seem like it
def pageToPageToken(page):
    return "v1:{}".format(page)

# Single-page search function for pagination control
def search_page(
    keywords,
    sort=MercariSort.SORT_CREATED_TIME,
    order=MercariOrder.ORDER_DESC,
    status=MercariSearchStatus.ON_SALE,
    exclude_keywords="",
    category_ids=None,
    brand_ids=None,
    page_token=None,
    page_limit=120
):
    """
    Search for a single page of results.

    Args:
        keywords (str): Search keywords
        sort (str): Sort method (use MercariSort constants)
        order (str): Sort order (use MercariOrder constants)
        status (str): Item status filter (use MercariSearchStatus constants)
        exclude_keywords (str): Keywords to exclude from results
        category_ids (list, optional): List of category IDs to filter by
        brand_ids (list, optional): List of brand IDs to filter by
        page_token (str, optional): Token for pagination (None for first page)
        page_limit (int): Items per page (1-120, default 120)

    Returns:
        tuple: (items, next_page_token) where next_page_token is None if no more pages
    """
    # Clamp page limit between 1 and 120
    limit = max(1, min(120, page_limit))

    # Build search condition
    search_condition = {
        "keyword": keywords,
        "sort": sort,
        "order": order,
        "status": [status],
        "excludeKeyword": exclude_keywords,
    }

    # Add category filtering if provided
    if category_ids is not None and len(category_ids) > 0:
        search_condition["categoryIds"] = category_ids

    # Add brand filtering if provided
    if brand_ids is not None and len(brand_ids) > 0:
        search_condition["brandIds"] = brand_ids

    data = {
        "userId": "MERCARI_BOT_{}".format(uuid.uuid4()),
        "pageSize": limit,
        "pageToken": page_token or pageToPageToken(0),
        "searchSessionId": "MERCARI_BOT_{}".format(uuid.uuid4()),
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "searchCondition": search_condition,
        "withAuction": True,
        "defaultDatasets": [
            "DATASET_TYPE_MERCARI",
            "DATASET_TYPE_BEYOND"
        ]
    }

    items, has_next, next_token = fetch(searchURL, data, parse)
    return items, next_token if has_next else None


# returns an generator for Item objects
# keeps searching until no results so may take a while to get results back

def search(
    keywords,
    sort=MercariSort.SORT_CREATED_TIME,
    order=MercariOrder.ORDER_DESC,
    status=MercariSearchStatus.ON_SALE,
    exclude_keywords="",
    category_ids=None,
    brand_ids=None,
    page_limit=120
):
    """
    Search Mercari for items matching the given criteria.

    Args:
        keywords (str): Search keywords
        sort (str): Sort method (use MercariSort constants)
        order (str): Sort order (use MercariOrder constants)
        status (str): Item status filter (use MercariSearchStatus constants)
        exclude_keywords (str): Keywords to exclude from results
        category_ids (list, optional): List of category IDs to filter by
        brand_ids (list, optional): List of brand IDs to filter by
        page_limit (int): Items per page (1-120, default 120)

    Yields:
        Item: Search result items
    """
    # Clamp page limit between 1 and 120
    limit = max(1, min(120, page_limit))

    # Build search condition with optional filtering
    search_condition = {
        "keyword": keywords,
        "sort": sort,
        "order": order,
        "status": [status],
        "excludeKeyword": exclude_keywords,
    }

    # Add category filtering if provided
    if category_ids is not None and len(category_ids) > 0:
        search_condition["categoryIds"] = category_ids

    # Add brand filtering if provided
    if brand_ids is not None and len(brand_ids) > 0:
        search_condition["brandIds"] = brand_ids

    data = {
        # this seems to be random, but we'll add a prefix for mercari to track if they wanted to
        "userId": "MERCARI_BOT_{}".format(uuid.uuid4()),
        "pageSize": limit,
        "pageToken": pageToPageToken(0),
        # same thing as userId, courtesy of a prefix for mercari
        "searchSessionId": "MERCARI_BOT_{}".format(uuid.uuid4()),
        # this is hardcoded in their frontend currently, so leaving it
        "indexRouting": "INDEX_ROUTING_UNSPECIFIED",
        "searchCondition": search_condition,
        "withAuction": True,
        # I'm not certain what these are, but I believe it's what mercari queries against
        # this is the default in their site, so leaving it as these 2
        "defaultDatasets": [
            "DATASET_TYPE_MERCARI",
            "DATASET_TYPE_BEYOND"
        ]
    }

    has_next_page = True

    while has_next_page:
        items, has_next_page, next_page_token = fetch(searchURL, data, parse)
        yield from items
        data['pageToken'] = next_page_token


def getItemInfo(itemID, country_code="JP"):
    data = {
        "id": itemID,
        "country_code": country_code,
        "include_item_attributes": True,
        "include_product_page_component": True,
        "include_non_ui_item_attributes": True,
        "include_donation": True,
        "include_offer_like_coupon_display": True,
        "include_offer_coupon_display": True,
        "include_item_attributes_sections": True,
        "include_auction": True
    }

    item = fetch(itemInfoURL, data, parseItemInfo, method="GET")
    return item