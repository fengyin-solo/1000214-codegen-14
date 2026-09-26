"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import script as router_script
from app.routers import scene as router_scene
from app.routers import casting as router_casting
from app.routers import crew as router_crew
from app.routers import notice as router_notice
from app.routers import location as router_location
from app.routers import prop as router_prop
from app.routers import costume as router_costume
from app.routers import makeup as router_makeup
from app.routers import equipment as router_equipment
from app.routers import shooting as router_shooting
from app.routers import footage as router_footage
from app.routers import edit as router_edit
from app.routers import vfx as router_vfx
from app.routers import vfx_vendor as router_vfx_vendor
from app.routers import review as router_review
from app.routers import budget as router_budget
from app.routers import expense as router_expense
from app.routers import schedule as router_schedule
from app.routers import permit as router_permit
from app.routers import wrap as router_wrap

ROUTERS = [router_script, router_scene, router_casting, router_crew, router_notice, router_location, router_prop, router_costume, router_makeup, router_equipment, router_shooting, router_footage, router_edit, router_vfx, router_vfx_vendor, router_review, router_budget, router_expense, router_schedule, router_permit, router_wrap]
