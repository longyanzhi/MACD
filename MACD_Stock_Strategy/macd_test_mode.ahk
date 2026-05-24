; ============================================================
; MACD 全自动交易测试器 (AHK v2)
;
; 功能：模拟 9:20-9:31 开盘前全流程测试
;   F5 - 完整流程（选股→开盘价检查→买入）
;   F6 - 选股
;   F7 - 开盘价检查
;   F8 - MACD监控测试（需先有持仓）
;   F9 - 查看持仓状态
;   F10 - 重置所有
;   F11 - 东方财富买入测试
;
; 注意：测试前请确保东方财富模拟盘已打开
; ============================================================
#Requires AutoHotkey v2.0
#SingleInstance Force
SetTitleMatchMode 2

; --- 配置区（与 macd_auto_trader.ahk 保持一致）---
PYTHON_PATH        := "C:\Users\35223\miniconda3\envs\MACD\python.exe"
SCANNER_SCRIPT     := "C:\Users\35223\MACD\MACD_Stock_Strategy\realtime_scanner.py"
MONITOR_SCRIPT     := "C:\Users\35223\MACD\MACD_Stock_Strategy\realtime_macd_monitor.py"
CHECK_OPEN_SCRIPT  := "C:\Users\35223\MACD\MACD_Stock_Strategy\check_open_price.py"
POS_MANAGER        := "C:\Users\35223\MACD\MACD_Stock_Strategy\position_manager.py"
BUY_SIGNAL    := "C:\Users\35223\MACD\MACD_Stock_Strategy\buy_signal.txt"
SELL_SIGNAL   := "C:\Users\35223\MACD\MACD_Stock_Strategy\sell_signal.txt"
SIGNAL_FILE   := "C:\Users\35223\MACD\MACD_Stock_Strategy\signals.txt"

; ===== 东方财富模拟盘鼠标坐标 =====
STOCK_CODE_X  := 316    ; 股票代码输入框 X
STOCK_CODE_Y  := 791    ; 股票代码输入框 Y
SHARES_X      := 298    ; 数量输入框 X
SHARES_Y      := 912    ; 数量输入框 Y
BUY_BTN_X     := 302    ; 买入按钮 X
BUY_BTN_Y     := 946    ; 买入按钮 Y
INSURE_X      := 53    ; 确认按钮 X
INSURE_Y      := 320    ; 确认按钮 Y
CLOSE_WIN_X   := 128
CLOSE_WIN_Y   := 164
SELL_BTN_X    := 302    ; 卖出按钮 X
SELL_BTN_Y    := 946    ; 卖出按钮 Y
; --- 配置区结束 ---

; 全局状态（与 macd_auto_trader.ahk 一致）
global current_action := "等待"

; ===== 热键 =====
F5::TestFullFlow()           ; 完整流程测试
F6::TestStockSelection()     ; 选股
F7::TestOpenPriceCheck()     ; 开盘价检查
F8::TestMacdMonitor()        ; MACD监控
F9::TestShowStatus()         ; 查看状态
F10::TestResetAll()          ; 重置所有
F11::TestEastMoneyBuy()      ; 东方财富买入测试

; ============================================================
; F5: 完整流程测试（模拟 9:20→9:26→9:31）
; ============================================================
TestFullFlow(*) {
    global current_action

    if MsgBox("确定要执行完整流程测试吗？`n`n将按顺序执行：`n  1. 选股（9:20）`n  2. 开盘价检查（9:26）`n  3. 买入（9:31）`n`n请确保东方财富模拟盘已打开", "完整流程测试", "OKCancel") = "Cancel"
        return

    ; ========== 步骤1：选股 ==========
    current_action := "选股"
    ShowTip("9:20 - 正在选股...")

    ToolTip "=== 完整流程测试 ===`n步骤1/3: 运行选股脚本..."
    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" reset'
    RunWait '"' . PYTHON_PATH . '" "' . SCANNER_SCRIPT . '"'

    if !FileExist(BUY_SIGNAL) {
        ToolTip
        MsgBox "今日无信号股，测试结束", "测试完成", "Iconi"
        current_action := "无信号"
        return
    }

    if code = "" {
        content := FileRead(BUY_SIGNAL)
        Loop Parse, content, "`n", "`r" {
            if A_LoopField = "" or InStr(A_LoopField, "#")
                continue
            fields := StrSplit(A_LoopField, "|")
            if fields.Length >= 1 {
                code := fields[1]
                break
            }
        }
    }

    if code = "" {
        ToolTip
        MsgBox "无法读取信号", "错误", "Icon!"
        current_action := "无信号"
        return
    }

    ; 写入买入信号（UTF-8 with BOM）
    FileDelete SIGNAL_FILE
    content := code . "|BUY|" . A_DD . "-" . A_MM . "-" . A_YYYY . "`n"
    ; 写入 BOM + UTF-8 内容
    FileAppend  content, SIGNAL_FILE, "UTF-8"

    current_action := "选股完成"
    ToolTip
    sel_result := MsgBox("选股完成`n`n  股票: " . code . "`n`n点击确定继续开盘价检查（9:26）", "选股结果", "OKCancel")
    if sel_result = "Cancel"
        return

    ; ========== 步骤2：开盘价检查 ==========
    current_action := "开盘价检查"
    ShowTip("9:26 - 检查开盘价偏离...")

    ToolTip "=== 完整流程测试 ===`n步骤2/3: 检查开盘价偏离..."
    RunWait '"' . PYTHON_PATH . '" "' . CHECK_OPEN_SCRIPT . '"'

    deviation := ""
    if FileExist(BUY_SIGNAL) {
        content := FileRead(BUY_SIGNAL)
        Loop Parse, content, "`n", "`r" {
            if InStr(A_LoopField, "开盘偏离:") {
                deviation := StrReplace(A_LoopField, "开盘偏离:")
                deviation := Trim(deviation)
                if InStr(deviation, "%")
                    deviation := StrReplace(deviation, "%")
            }
        }
    }

    deviation_val := Number(deviation = "" ? 0 : deviation)
    ToolTip

    if deviation_val > 3 {
        MsgBox "开盘价偏离 " . deviation . "%，超过3%，放弃本次信号", "开盘价检查", "Iconx"
        current_action := "放弃信号"
        return
    }

    current_action := "待买入"
    confirm := MsgBox("开盘价正常（偏离: " . deviation . "%）`n`n即将在东方财富买入：`n  股票: " . code . "`n  数量: 100 股`n`n点击确定开始买入（9:31）", "买入确认", "OKCancel")
    if confirm = "Cancel"
        return

    ; ========== 步骤3：买入 ==========
    current_action := "买入"
    ShowTip("9:31 - 自动买入...")

    ToolTip "=== 完整流程测试 ===`n步骤3/3: 在东方财富买入..."
    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" buy ' . code

    ; 东方财富买入
    if !JumpToEastMoney()
        return

    ; 填入股票代码（去掉 .SH/.SZ 后缀）
    code := StripCodeSuffix(code)
    MouseMove STOCK_CODE_X, STOCK_CODE_Y, 10
    Click
    Send "^a{Del}" . code
    Sleep 500

    ; 填入数量 100 股
    MouseMove SHARES_X, SHARES_Y, 10
    Click
    Send "^a{Del}100"
    Sleep 300

    ; 点击买入按钮
    MouseMove BUY_BTN_X, BUY_BTN_Y, 10
    Click

    current_action := "持仓中"
    ShowTip("已买入: " . code)
    ToolTip
    MsgBox "完整流程测试完成！`n`n  股票: " . code . "`n  数量: 100 股`n  状态: 持仓中`n`n可在14:55按F8测试MACD监控卖出", "测试完成", "Iconi"
}


; ============================================================
; F6: 选股测试
; ============================================================
TestStockSelection(*) {
    global current_action

    ToolTip "测试: 运行选股脚本..."
    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" reset'
    RunWait '"' . PYTHON_PATH . '" "' . SCANNER_SCRIPT . '"'

    ToolTip
    if !FileExist(BUY_SIGNAL) {
        MsgBox "今日无金叉信号股", "选股测试", "Iconi"
        current_action := "无信号"
        return
    }

    code := ""
    count := 0

    if FileExist(SIGNAL_FILE) {
        content := FileRead(SIGNAL_FILE)
        Loop Parse, content, "`n", "`r" {
            if InStr(A_LoopField, "#") or A_LoopField = ""
                continue
            count++
            if code = "" {
                fields := StrSplit(A_LoopField, "|")
                if fields.Length >= 2
                    code := fields[2]
            }
        }
    }

    if code = "" and FileExist(BUY_SIGNAL) {
        content := FileRead(BUY_SIGNAL)
        Loop Parse, content, "`n", "`r" {
            if A_LoopField = "" or InStr(A_LoopField, "#")
                continue
            count++
            if code = "" {
                fields := StrSplit(A_LoopField, "|")
                if fields.Length >= 1
                    code := fields[1]
            }
            break
        }
    }

    current_action := "选股完成"
    MsgBox "发现 " . count . " 只信号股`n`n最优信号: " . code, "选股测试成功", "Iconi"
}


; ============================================================
; F7: 开盘价检查测试
; ============================================================
TestOpenPriceCheck(*) {
    global current_action

    if !FileExist(BUY_SIGNAL) {
        MsgBox "请先运行选股（F6）`n`n查找文件：" . BUY_SIGNAL, "提示", "Icon?"
        return
    }

    code := ""
    content := FileRead(BUY_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if A_LoopField = "" or InStr(A_LoopField, "#")
            continue
        fields := StrSplit(A_LoopField, "|")
        if fields.Length >= 1 {
            code := fields[1]
            break
        }
    }

    if code = "" {
        MsgBox "无法读取股票代码", "错误", "Icon!"
        return
    }

    ToolTip "检查 " . code . " 的开盘价偏离..."
    RunWait '"' . PYTHON_PATH . '" "' . CHECK_OPEN_SCRIPT . '"'

    deviation := ""
    content := FileRead(BUY_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if InStr(A_LoopField, "开盘偏离:") {
            deviation := StrReplace(A_LoopField, "开盘偏离:")
            deviation := Trim(deviation)
            if InStr(deviation, "%")
                deviation := StrReplace(deviation, "%")
        }
    }

    deviation_val := Number(deviation = "" ? 0 : deviation)
    ToolTip

    if deviation_val > 3 {
        MsgBox "开盘价偏离 " . deviation . "%，超过3%，放弃本次信号", "开盘价检查", "Iconx"
        current_action := "放弃信号"
    } else {
        current_action := "待买入"
        MsgBox "开盘价正常（偏离: " . deviation . "%）`n`n当前状态: 待买入`n可在9:31按F5完整流程测试买入", "开盘价检查", "Iconi"
    }
}


; ============================================================
; F8: MACD监控测试
; ============================================================
TestMacdMonitor(*) {
    global current_action

    state_file := "C:\Users\35223\MACD\MACD_Stock_Strategy\position_state.json"
    if !FileExist(state_file) {
        MsgBox "当前无持仓，请先执行完整流程测试（F5）", "提示", "Icon?"
        return
    }

    ToolTip "测试: 运行MACD监控..."
    RunWait '"' . PYTHON_PATH . '" "' . MONITOR_SCRIPT . '"'

    ToolTip
    if !FileExist(SELL_SIGNAL) {
        current_action := "持仓中"
        MsgBox "MACD未下降，继续持有", "MACD监控结果", "Iconi"
        return
    }

    code := ""
    reason := ""
    content := FileRead(SELL_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if A_Index = 1 {
            fields := StrSplit(A_LoopField, "|")
            code := fields[1]
        }
        if InStr(A_LoopField, "原因:")
            reason := StrReplace(A_LoopField, "原因:")
    }

    ; 确认卖出
    confirm := MsgBox("触发卖出信号！`n`n  股票: " . code . "`n  原因: " . reason . "`n`n是否确认在东方财富卖出？", "MACD监控结果", "OKCancel")
    if confirm = "Cancel"
        return

    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" sell'

    ; 东方财富卖出
    if !JumpToEastMoney()
        return

    ; 填入卖出数量（不填股票代码，卖出界面已有）
    MouseMove SHARES_X, SHARES_Y, 10
    Click
    Send "^a{Del}"
    Send "100"
    Sleep 1000

    ; 点击卖出按钮
    MouseMove SELL_BTN_X, SELL_BTN_Y, 10
    Click
    Sleep 1000

    ; 点击确认按钮
    MouseMove INSURE_X, INSURE_Y, 10
    Click
    Sleep 500

    ; 关闭窗口
    MouseMove CLOSE_WIN_X, CLOSE_WIN_Y, 10
    Click

    current_action := "已卖出"
    ShowTip("已卖出: " . code)
    MsgBox "MACD监控测试完成`n`n  股票: " . code . "`n  原因: " . reason . "`n  状态: 已卖出", "测试完成", "Iconi"
}


; ============================================================
; F9: 查看持仓状态
; ============================================================
TestShowStatus(*) {
    ToolTip "查看持仓状态..."
    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" status'

    ToolTip
    state_file := "C:\Users\35223\MACD\MACD_Stock_Strategy\position_state.json"
    if FileExist(state_file)
        Run "notepad.exe `"" . state_file . "`""
    else
        MsgBox "持仓状态文件不存在", "提示", "Icon?"
}


; ============================================================
; F10: 重置所有
; ============================================================
TestResetAll(*) {
    if MsgBox("确定要重置所有状态吗？`n`n这将清空持仓记录，重新开始", "重置确认", "OKCancel") = "Cancel"
        return

    ToolTip "正在重置..."
    RunWait '"' . PYTHON_PATH . '" "' . POS_MANAGER . '" reset'

    if FileExist(BUY_SIGNAL)
        FileDelete BUY_SIGNAL
    if FileExist(SELL_SIGNAL)
        FileDelete SELL_SIGNAL

    global current_action := "等待"
    ToolTip
    MsgBox "所有状态和信号文件已清空", "重置完成", "Iconi"
}


; ============================================================
; F11: 东方财富买入测试（独立测试）
; ============================================================
TestEastMoneyBuy(*) {
    if !FileExist(BUY_SIGNAL) {
        MsgBox "请先运行选股（F6）或完整流程测试（F5）`n`n查找文件：" . BUY_SIGNAL, "提示", "Icon?"
        return
    }

    ; 读取股票代码
    code := ""
    content := FileRead(BUY_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if A_LoopField = "" or InStr(A_LoopField, "#")
            continue
        fields := StrSplit(A_LoopField, "|")
        if fields.Length >= 1 {
            code := fields[2]
            break
        }
    }

    if code = "" {
        MsgBox "无法读取股票代码", "错误", "Icon!"
        return
    }

    ; 东方财富买入（鼠标点击方式）
    if !JumpToEastMoney()
        return

    ; 填入股票代码（去掉 .SH/.SZ 后缀）
    code := StripCodeSuffix(code)
    ToolTip "填入股票代码: " . code
    MouseMove STOCK_CODE_X, STOCK_CODE_Y, 10
    Click
    Send "^a{Del}" . code
    Sleep 500

    ToolTip "填入数量: 100"
    MouseMove SHARES_X, SHARES_Y, 10
    Click
    Send "^a{Del}100"
    Sleep 1000

    ToolTip "点击买入按钮..."
    MouseMove BUY_BTN_X, BUY_BTN_Y, 10
    Click
    Sleep 1000

    ToolTip "点击确认按钮..."
    MouseMove INSURE_X, INSURE_Y, 10
    Click
    Sleep 2000

    ToolTip "关闭窗口"
    MouseMove CLOSE_WIN_X, CLOSE_WIN_Y, 10
    Click
}


; ============================================================
; 工具函数
; ============================================================

; 去掉股票代码的后缀（如 .SH .SZ .sh .sz），只保留纯代码
StripCodeSuffix(code) {
    ; 去掉 .SH 或 .SZ 后缀（大小写兼容）
    code := RegExReplace(code, "i)\.(SH|SZ)$", "")
    return Trim(code)
}

; 跳转到东方财富（与 macd_auto_trader.ahk 一致）
; 返回 true 表示成功激活并就绪，返回 false 表示失败
JumpToEastMoney() {
    ; 检查东方财富进程是否存在
    if !WinExist("ahk_exe mainfree.exe") {
        MsgBox "未找到东方财富窗口`n`n请先打开东方财富模拟盘", "错误", "IconX"
        return false
    }

    ; 激活窗口
    WinActivate
    Sleep 300

    ; 等待窗口变为活动状态（最多3秒）
    loop 6 {
        if WinActive("ahk_exe mainfree.exe")
            break
        Sleep 500
    }

    if !WinActive("ahk_exe mainfree.exe") {
        MsgBox "东方财富窗口激活失败`n`n请手动激活东方财富窗口后重试", "错误", "IconX"
        return false
    }

    ; 额外等待，确保窗口完全就绪可交互
    Sleep 300
    return true
}


ShowTip(msg) {
    TrayTip("MACD 测试", msg, 10)
    ToolTip(msg, 0, 0)
    SetTimer(RemoveTip, -3000)
}


RemoveTip() {
    ToolTip
}


; ============================================================
; 托盘菜单
; ============================================================
Tray := A_TrayMenu
Tray.Delete()
Tray.Add("完整流程测试 (F5)", TestFullFlow)
Tray.Add("选股测试 (F6)", TestStockSelection)
Tray.Add("开盘价检查 (F7)", TestOpenPriceCheck)
Tray.Add("MACD监控测试 (F8)", TestMacdMonitor)
Tray.Add("查看状态 (F9)", TestShowStatus)
Tray.Add("重置所有 (F10)", TestResetAll)
Tray.Add("东方财富买入测试 (F11)", TestEastMoneyBuy)
Tray.Add
Tray.Add("退出", (*) => ExitApp())
Tray.Default := "完整流程测试 (F5)"
Tray.ClickCount := 1

ToolTip "MACD 测试模式已启动`n按 F5-F11 测试各功能`nF5 = 完整流程"
Sleep 3000
ToolTip
