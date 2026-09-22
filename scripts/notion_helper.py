import logging
import os
import re

from notion_client import Client
from retrying import retry
from dotenv import load_dotenv

load_dotenv()

from utils import (
    format_date,
    get_date,
    get_first_and_last_day_of_month,
    get_first_and_last_day_of_week,
    get_first_and_last_day_of_year,
    get_icon,
    get_relation,
    get_title,
)


TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TARGET_ICON_URL = "https://www.notion.so/icons/target_red.svg"
BOOKMARK_ICON_URL = "https://www.notion.so/icons/bookmark_gray.svg"


class NotionHelper:

    database_name_dict = {
        "PODCAST_DATABASE_NAME": "Podcast",
        "EPISODE_DATABASE_NAME": "Episode",
        "ALL_DATABASE_NAME": "全部",
        "AUTHOR_DATABASE_NAME": "Author",
    }

    # Database ID
    database_id_dict = {}

    # Data Source ID
    data_source_id_dict = {}

    image_dict = {}

    def __init__(self):

        self.client = Client(
            auth=os.getenv("NOTION_TOKEN"),
            log_level=logging.ERROR,
        )

        self.__cache = {}

        notion_page = os.getenv("NOTION_PAGE")

        if not notion_page:
            raise Exception(
                "NOTION_PAGE 未设置，请检查 GitHub Secrets 中的 NOTION_PAGE"
            )

        self.page_id = self.extract_page_id(notion_page)

        # 找到页面下的 Database
        self.search_database(self.page_id)

        # 允许通过环境变量修改数据库名称
        for key in self.database_name_dict.keys():
            value = os.getenv(key)

            if value is not None and value != "":
                self.database_name_dict[key] = value

        # Podcast
        self.podcast_database_id = self.database_id_dict.get(
            self.database_name_dict.get("PODCAST_DATABASE_NAME")
        )

        self.podcast_data_source_id = self.data_source_id_dict.get(
            self.database_name_dict.get("PODCAST_DATABASE_NAME")
        )

        # Episode
        self.episode_database_id = self.database_id_dict.get(
            self.database_name_dict.get("EPISODE_DATABASE_NAME")
        )

        self.episode_data_source_id = self.data_source_id_dict.get(
            self.database_name_dict.get("EPISODE_DATABASE_NAME")
        )

        # Author
        self.author_database_id = self.database_id_dict.get(
            self.database_name_dict.get("AUTHOR_DATABASE_NAME")
        )

        self.author_data_source_id = self.data_source_id_dict.get(
            self.database_name_dict.get("AUTHOR_DATABASE_NAME")
        )

        # 全部
        self.all_database_id = self.database_id_dict.get(
            self.database_name_dict.get("ALL_DATABASE_NAME")
        )

        self.all_data_source_id = self.data_source_id_dict.get(
            self.database_name_dict.get("ALL_DATABASE_NAME")
        )

        # 检查数据库
        self._check_databases()

    # ============================================================
    # Notion ID
    # ============================================================

    def extract_page_id(self, notion_url):

        if not notion_url:
            raise Exception(
                "获取NotionID失败：NOTION_PAGE 为空"
            )

        # 匹配 32 位 ID 或 UUID
        match = re.search(
            r"([a-f0-9]{32}|"
            r"[a-f0-9]{8}-"
            r"[a-f0-9]{4}-"
            r"[a-f0-9]{4}-"
            r"[a-f0-9]{4}-"
            r"[a-f0-9]{12})",
            notion_url,
        )

        if match:
            return match.group(0)

        raise Exception(
            "获取NotionID失败，请检查 NOTION_PAGE 的 Url 是否正确"
        )

    # ============================================================
    # 搜索 Database
    # ============================================================

    def search_database(self, block_id):

        try:
            children = self.client.blocks.children.list(
                block_id=block_id
            )["results"]

        except Exception as e:
            raise Exception(
                f"读取 Notion 页面失败，请确认 NOTION_TOKEN 和 NOTION_PAGE 权限：{e}"
            )

        for child in children:

            child_type = child.get("type")

            # ----------------------------------------------------
            # 找到 Database
            # ----------------------------------------------------
            if child_type == "child_database":

                database = child.get("child_database") or {}

                database_name = database.get("title")
                database_id = child.get("id")

                if database_name and database_id:

                    self.database_id_dict[
                        database_name
                    ] = database_id

                    # 获取对应 Data Source ID
                    data_source_id = self._get_data_source_id(
                        database_id
                    )

                    if data_source_id:
                        self.data_source_id_dict[
                            database_name
                        ] = data_source_id

                    print(
                        f"发现 Notion 数据库：{database_name}"
                    )

                    print(
                        f"  Database ID: {database_id}"
                    )

                    if data_source_id:
                        print(
                            f"  Data Source ID: {data_source_id}"
                        )
                    else:
                        print(
                            f"  ⚠️ 未找到 Data Source ID：{database_name}"
                        )

            # ----------------------------------------------------
            # 递归搜索子块
            # ----------------------------------------------------
            if child.get("has_children"):

                self.search_database(
                    child.get("id")
                )

    # ============================================================
    # 获取 Data Source ID
    # ============================================================

    def _get_data_source_id(self, database_id):

        if not database_id:
            return None

        # --------------------------------------------------------
        # 方法 1：从 Database retrieve 响应中寻找 data_sources
        # --------------------------------------------------------
        try:

            response = self.client.databases.retrieve(
                database_id=database_id
            )

            data_sources = response.get("data_sources")

            if data_sources:

                # 通常是：
                # [
                #     {
                #         "id": "...",
                #         "name": "..."
                #     }
                # ]

                first = data_sources[0]

                if isinstance(first, dict):

                    data_source_id = first.get("id")

                    if data_source_id:
                        return data_source_id

        except Exception as e:

            print(
                f"⚠️ 获取 Data Source 失败：{database_id}，{e}"
            )

        # --------------------------------------------------------
        # 方法 2：
        # 某些旧版/特殊数据库结构下，Database ID 本身可能可以使用
        # --------------------------------------------------------

        try:

            response = self.client.data_sources.retrieve(
                data_source_id=database_id
            )

            if response and response.get("id"):
                return response.get("id")

        except Exception:
            pass

        return None

    # ============================================================
    # 检查数据库
    # ============================================================

    def _check_databases(self):

        required = {
            "Podcast": (
                self.podcast_database_id,
                self.podcast_data_source_id,
            ),
            "Episode": (
                self.episode_database_id,
                self.episode_data_source_id,
            ),
            "Author": (
                self.author_database_id,
                self.author_data_source_id,
            ),
            "全部": (
                self.all_database_id,
                self.all_data_source_id,
            ),
        }

        print("")
        print("========== Notion 数据库检查 ==========")

        for name, values in required.items():

            database_id, data_source_id = values

            if database_id:

                print(
                    f"✓ {name} Database ID: {database_id}"
                )

            else:

                print(
                    f"⚠️ {name} Database 未找到"
                )

            if data_source_id:

                print(
                    f"✓ {name} Data Source ID: {data_source_id}"
                )

            else:

                print(
                    f"⚠️ {name} Data Source 未找到"
                )

        print("========================================")
        print("")

    # ============================================================
    # 更新图片
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def update_image_block_link(
        self,
        block_id,
        new_image_url
    ):

        return self.client.blocks.update(
            block_id=block_id,
            image={
                "external": {
                    "url": new_image_url
                }
            },
        )

    # ============================================================
    # 周
    # ============================================================

    def get_week_relation_id(self, date):

        year = date.isocalendar().year
        week = date.isocalendar().week

        week = f"{year}年第{week}周"

        start, end = get_first_and_last_day_of_week(
            date
        )

        properties = {
            "日期": get_date(
                format_date(start),
                format_date(end)
            )
        }

        return self.get_relation_id(
            week,
            self.week_database_id,
            TARGET_ICON_URL,
            properties,
        )

    # ============================================================
    # 月
    # ============================================================

    def get_month_relation_id(self, date):

        month = date.strftime("%Y年%-m月")

        start, end = get_first_and_last_day_of_month(
            date
        )

        properties = {
            "日期": get_date(
                format_date(start),
                format_date(end)
            )
        }

        return self.get_relation_id(
            month,
            self.month_database_id,
            TARGET_ICON_URL,
            properties,
        )

    # ============================================================
    # 年
    # ============================================================

    def get_year_relation_id(self, date):

        year = date.strftime("%Y")

        start, end = get_first_and_last_day_of_year(
            date
        )

        properties = {
            "日期": get_date(
                format_date(start),
                format_date(end)
            )
        }

        return self.get_relation_id(
            year,
            self.year_database_id,
            TARGET_ICON_URL,
            properties,
        )

    # ============================================================
    # 日
    # ============================================================

    def get_day_relation_id(self, date):

        new_date = date.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        day = new_date.strftime(
            "%Y年%m月%d日"
        )

        properties = {
            "日期": get_date(
                format_date(date)
            )
        }

        properties["年"] = get_relation(
            [
                self.get_year_relation_id(
                    new_date
                )
            ]
        )

        properties["月"] = get_relation(
            [
                self.get_month_relation_id(
                    new_date
                )
            ]
        )

        properties["周"] = get_relation(
            [
                self.get_week_relation_id(
                    new_date
                )
            ]
        )

        return self.get_relation_id(
            day,
            self.day_database_id,
            TARGET_ICON_URL,
            properties,
        )

    # ============================================================
    # 获取 Relation ID
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def get_relation_id(
        self,
        name,
        id,
        icon,
        properties=None
    ):

        if properties is None:
            properties = {}

        key = f"{id}{name}"

        if key in self.__cache:
            return self.__cache.get(key)

        filter_data = {
            "property": "标题",
            "title": {
                "equals": name
            }
        }

        # --------------------------------------------------------
        # 根据 Database ID 找 Data Source ID
        # --------------------------------------------------------

        data_source_id = None

        for database_name, database_id in self.database_id_dict.items():

            if database_id == id:

                data_source_id = (
                    self.data_source_id_dict.get(
                        database_name
                    )
                )

                break

        # --------------------------------------------------------
        # 如果找不到 Data Source，尝试直接转换
        # --------------------------------------------------------

        if not data_source_id:

            data_source_id = self._get_data_source_id(id)

        if not data_source_id:

            raise Exception(
                f"找不到 Notion Data Source ID。"
                f"Database ID={id}，名称={name}。"
                f"请确认 NOTION_TOKEN 对该数据库有访问权限。"
            )

        # --------------------------------------------------------
        # 新版 Notion API 查询
        # --------------------------------------------------------

        response = self.client.data_sources.query(
            data_source_id=data_source_id,
            filter=filter_data,
        )

        results = response.get(
            "results",
            []
        )

        # --------------------------------------------------------
        # 不存在则创建
        # --------------------------------------------------------

        if len(results) == 0:

            parent = {
                "database_id": id,
                "type": "database_id",
            }

            properties["标题"] = get_title(name)

            page_id = self.client.pages.create(
                parent=parent,
                properties=properties,
                icon=get_icon(icon),
            ).get("id")

        else:

            page_id = results[0].get("id")

        self.__cache[key] = page_id

        return page_id

    # ============================================================
    # 更新页面
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def update_book_page(
        self,
        page_id,
        properties
    ):

        return self.client.pages.update(
            page_id=page_id,
            properties=properties,
        )

    # ============================================================
    # 更新页面
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def update_page(
        self,
        page_id,
        properties
    ):

        return self.client.pages.update(
            page_id=page_id,
            properties=properties,
        )

    # ============================================================
    # 创建页面
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def create_page(
        self,
        parent,
        properties,
        icon
    ):

        return self.client.pages.create(
            parent=parent,
            properties=properties,
            icon=icon,
            cover=icon,
        )

    # ============================================================
    # 通用 Query
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def query(self, **kwargs):

        kwargs = {
            k: v
            for k, v in kwargs.items()
            if v is not None
        }

        database_id = kwargs.pop(
            "database_id",
            None
        )

        if not database_id:

            raise ValueError(
                "query() 缺少 database_id"
            )

        # --------------------------------------------------------
        # 找 Data Source ID
        # --------------------------------------------------------

        data_source_id = None

        for database_name, db_id in self.database_id_dict.items():

            if db_id == database_id:

                data_source_id = (
                    self.data_source_id_dict.get(
                        database_name
                    )
                )

                break

        if not data_source_id:

            data_source_id = self._get_data_source_id(
                database_id
            )

        if not data_source_id:

            raise Exception(
                f"找不到 Data Source ID："
                f"database_id={database_id}"
            )

        return self.client.data_sources.query(
            data_source_id=data_source_id,
            **kwargs
        )

    # ============================================================
    # 获取 Block Children
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def get_block_children(self, id):

        response = self.client.blocks.children.list(
            id
        )

        return response.get(
            "results",
            []
        )

    # ============================================================
    # 添加 Blocks
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def append_blocks(
        self,
        block_id,
        children
    ):

        return self.client.blocks.children.append(
            block_id=block_id,
            children=children,
        )

    # ============================================================
    # 在指定 Block 后添加
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def append_blocks_after(
        self,
        block_id,
        children,
        after
    ):

        return self.client.blocks.children.append(
            block_id=block_id,
            children=children,
            after=after,
        )

    # ============================================================
    # 删除 Block
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def delete_block(
        self,
        block_id
    ):

        return self.client.blocks.delete(
            block_id=block_id
        )

    # ============================================================
    # 查询全部
    # ============================================================

    @retry(
        stop_max_attempt_number=3,
        wait_fixed=5000
    )
    def query_all(
        self,
        database_id,
        filter
    ):

        results = []

        has_more = True
        start_cursor = None

        # --------------------------------------------------------
        # 找 Data Source ID
        # --------------------------------------------------------

        data_source_id = None

        for database_name, db_id in self.database_id_dict.items():

            if db_id == database_id:

                data_source_id = (
                    self.data_source_id_dict.get(
                        database_name
                    )
                )

                break

        if not data_source_id:

            data_source_id = self._get_data_source_id(
                database_id
            )

        if not data_source_id:

            raise Exception(
                f"找不到 Data Source ID："
                f"database_id={database_id}"
            )

        # --------------------------------------------------------
        # 分页查询
        # --------------------------------------------------------

        while has_more:

            request_args = {
                "data_source_id": data_source_id,
                "filter": filter,
                "page_size": 100,
            }

            if start_cursor:
                request_args["start_cursor"] = start_cursor

            response = self.client.data_sources.query(
                **request_args
            )

            start_cursor = response.get(
                "next_cursor"
            )

            has_more = response.get(
                "has_more",
                False
            )

            results.extend(
                response.get(
                    "results",
                    []
                )
            )

        return results
```
