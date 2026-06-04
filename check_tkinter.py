import sys
import os

python_dir = os.path.dirname(sys.executable)
print(f"Python 路径: {python_dir}")

# 检查关键文件
files_to_check = [
    os.path.join(python_dir, 'DLLs', '_tkinter.pyd'),
    os.path.join(python_dir, 'DLLs', 'tcl86t.dll'),
    os.path.join(python_dir, 'DLLs', 'tk86t.dll'),
    os.path.join(python_dir, 'tcl'),
]

print("\n检查 Tkinter 相关文件:")
for f in files_to_check:
    exists = os.path.exists(f)
    status = "✓ 存在" if exists else "✗ 缺失"
    print(f"  {status}: {f}")

print("\n尝试导入 tkinter...")
try:
    import tkinter
    print("✓ tkinter 导入成功")
except Exception as e:
    print(f"✗ tkinter 导入失败: {e}")

print("\n检查环境变量 TCL_LIBRARY...")
tcl_lib = os.environ.get('TCL_LIBRARY')
if tcl_lib:
    print(f"✓ TCL_LIBRARY: {tcl_lib}")
else:
    print("✗ TCL_LIBRARY 未设置")

input("\n按回车键退出...")