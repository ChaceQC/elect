"""按实际主键续扫，避免对整张热表计算/排序HEX字符串。"""


def scan(columns, after, *, text_first=False):
    parts = after.rsplit(":", len(columns)-1) if after else [""] * len(columns)
    if len(parts) != len(columns):
        raise ValueError("归档游标无效")
    values = [part if text_first and index == 0 else bytes.fromhex(part)
              for index, part in enumerate(parts)]
    params = {f"cursor_{i}": value for i, value in enumerate(values)}
    clauses = []
    for index, column in enumerate(columns):
        clauses.append("(" + " AND ".join(
            [f"{prior}=:cursor_{i}" for i, prior in enumerate(columns[:index])]
            + [f"{column}>:cursor_{index}"]) + ")")
    return "(" + " OR ".join(clauses) + ")", ",".join(columns), params
