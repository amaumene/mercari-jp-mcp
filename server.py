import logging
import os
from typing import Any, Dict, List, Optional, Protocol, Generator
from mercari import (MercariOrder, MercariSearchStatus, MercariSort, search)
from pydantic import Field
from fastmcp import FastMCP

# Initialize logger
logger = logging.getLogger(__name__)

# Configure logging format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Protocol for Item structure from mercari library
class Item(Protocol):
    """Protocol defining the structure of Item objects from mercari.search()"""
    productName: str
    price: str | int | float
    productURL: str
    id: str


mcp = FastMCP(name="MercariSearchComplete")

@mcp.tool(name="search_mercari_jp",
                description="""Search Mercari for items, excluding keywords and filtering by price and specific model name.
                Args:
                    keyword (str): The main keyword to search for (e.g., 'iPhone15 Pro 256GB'). Optimize this to ensure the product name is correct, sometimes it has to be in Japanese.
                    exclude_keywords (str): Space-separated keywords to exclude. Think about exclude keywords that can make the search more precise. Generate this in japanese. For example, 'ジャンク', 'max', 'plus', '11', '12', '13', '14', '16', 'ケース', 'カバー', 'フィルム' when searching for iPhone15 Pro 256GB. Don't forget to separate them with space. Do not include '新品', '未使用', or '中古' in this list if not requested.
                    min_price (int, optional): Minimum price in JPY. Think about the minimum price that you are willing to pay for the item. For example, if you are looking for a new iPhone15 Pro 256GB, you might want to set a minimum price of 100000 JPY.
                    max_price (int, optional): Maximum price in JPY. Think about the maximum price that you are willing to pay for the item. For example, if you are looking for a new iPhone15 Pro 256GB, you might want to set a maximum price of 200000 JPY.""")
def search_mercari_items_filtered(
    keyword: str = Field(..., description="The main keyword to search for (e.g., 'iPhone15 Pro 256GB')."),
    exclude_keywords: str = Field("", description="Space-separated keywords to exclude (e.g., 'ジャンク max')."),
    min_price: Optional[int] = Field(None, description="Minimum price in JPY.", ge=0),
    max_price: Optional[int] = Field(None, description="Maximum price in JPY.", ge=0)
) -> List[Dict[str, Any]]:
    """
    Performs a search on Mercari Japan using a keyword, excluding specified keywords,
    and filtering results by the provided price range.
    Uses default sorting (price ascending) and only shows items on sale.

    Returns:
        A list of dictionaries for items matching all criteria.
        Returns an empty list if no items are found or an error occurs.
    """
    # Input validation
    if not keyword or not keyword.strip():
        logger.error("Keyword parameter is empty or contains only whitespace")
        return []

    if min_price is not None and max_price is not None and min_price > max_price:
        logger.error(f"Invalid price range: min_price ({min_price}) is greater than max_price ({max_price})")
        return []

    try:
        search_results: Generator[Item, None, None] = search(
            keyword,
            sort=MercariSort.SORT_SCORE,
            order=MercariOrder.ORDER_DESC,
            status=MercariSearchStatus.ON_SALE,
            exclude_keywords=exclude_keywords
        )

        items_found: List[Dict[str, Any]] = []

        for item in search_results:
            try:
                product_name: Optional[str] = getattr(item, 'productName', None)
                if product_name is None:
                    continue

                price_raw: Optional[str | int | float] = getattr(item, 'price', None)
                if price_raw is None:
                    continue

                try:
                    price: float = float(price_raw)
                except (ValueError, TypeError):
                    continue

                # Price filtering
                min_check_passed: bool = (min_price is None) or (price >= min_price)
                max_check_passed: bool = (max_price is None) or (price <= max_price)

                if min_check_passed and max_check_passed:
                    items_found.append({
                        "name": product_name,
                        "url": getattr(item, 'productURL', 'N/A'),
                        "price": price,
                    })

            except AttributeError as filter_err:
                logger.warning(f"Skipping item during post-filtering due to data access error: {filter_err}")
                continue
            except Exception as unexpected_err:
                logger.error(f"Skipping item due to unexpected error during filtering: {unexpected_err}")
                continue

        return items_found

    except Exception as e:
        logger.error(f"An error occurred during Mercari search: {e}")
        return []

if __name__ == "__main__":
    # For remote MCP server, use SSE transport
    import uvicorn
    host: str = os.getenv("MCP_HOST", "0.0.0.0")
    port: int = int(os.getenv("MCP_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)

    # Alternative: Run with uvicorn directly
    # uvicorn.run(mcp.get_asgi_app(), host=host, port=port)
