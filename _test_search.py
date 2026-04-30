import akshare as ak
df = ak.stock_search_em(keyword='贵州茅台')
print("columns:", list(df.columns))
print(df.head(3).to_string())
