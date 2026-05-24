; ============================================================
; MACD 全自动交易调度器 - 东方财富版 (AHK v2)
;
; 功能：自动在指定时间执行交易操作，无需人工干预
; 状态管理：完全由AHK通过状态文件管理
;
; 时间表：
;   9:20  → 自动运行选股脚本
;   9:30  → 自动检查开盘价偏离（偏离>3%则跳过）
;   9:31  → 自动买入最优信号股
;   14:55 → 自动运行MACD监控，触发卖出/止损
;   15:05 → 收盘后检查持仓，更新状态
;
; 状态文件：trading_state.json
; ============================================================
#SingleInstance Force
SetTitleMatchMode 2
CoordMode "ToolTip", "Screen"

; --- 配置区 ---
PYTHON_PATH    := "C:\Users\35223\miniconda3\envs\MACD\python.exe"
SCANNER_SCRIPT := "C:\Users\35223\MACD\MACD_Stock_Strategy\realtime_scanner.py"
MONITOR_SCRIPT := "C:\Users\35223\MACD\MACD_Stock_Strategy\realtime_macd_monitor.py"
CHECK_OPEN_SCRIPT := "C:\Users\35223\MACD\MACD_Stock_Strategy\check_open_price.py"
BUY_SIGNAL    := "C:\Users\35223\MACD\MACD_Stock_Strategy\buy_signal.txt"
SELL_SIGNAL   := "C:\Users\35223\MACD\MACD_Stock_Strategy\sell_signal.txt"
SIGNAL_FILE   := "C:\Users\35223\MACD\MACD_Stock_Strategy\signals.txt"
STATE_FILE    := "C:\Users\35223\MACD\MACD_Stock_Strategy\trading_state.json"

AUTO_MODE     := true   ; true = 全自动，false = 半自动（保留确认）

; ===== 东方财富模拟盘鼠标坐标 =====
STOCK_CODE_X  := 316    ; 股票代码输入框 X
STOCK_CODE_Y  := 791    ; 股票代码输入框 Y
SHARES_X      := 298    ; 数量输入框 X
SHARES_Y      := 912    ; 数量输入框 Y
BUY_BTN_X     := 302    ; 买入按钮 X
BUY_BTN_Y     := 946    ; 买入按钮 Y
INSURE_X      := 53     ; 确认按钮 X
INSURE_Y      := 320    ; 确认按钮 Y
CLOSE_WIN_X   := 128    ; 关闭窗口 X
CLOSE_WIN_Y   := 164    ; 关闭窗口 Y
SELL_BTN_X    := 302    ; 卖出按钮 X
SELL_BTN_Y    := 946    ; 卖出按钮 Y
DEPUTE_SELL_X := 115    ; 委托卖出 X
DEPUTE_SELL_Y := 838    ; 委托卖出 Y
; --- 配置区结束 ---

; ============================================================
; 状态管理函数（JSON文件操作）
; ============================================================

; 读取状态文件
ReadState() {
    global STATE_FILE
    if (!FileExist(STATE_FILE)) {
        return {status: "IDLE", stock_code: "", buy_date: "", buy_price: 0, sell_today_flag: false, last_updated: ""}
    }
    
    content := FileRead(STATE_FILE)
    try {
        state := Json.Load(content)
        return state
    } catch {
        return {status: "IDLE", stock_code: "", buy_date: "", buy_price: 0, sell_today_flag: false, last_updated: ""}
    }
}

; 保存状态文件
WriteState(state) {
    global STATE_FILE
    state["last_updated"] := FormatTime(, "yyyy-MM-dd HH:mm:ss")
    content := Json.Stringify(state)
    FileDelete STATE_FILE
    FileAppend content, STATE_FILE, "UTF-8"
}

; 获取当前状态字符串
GetCurrentStatus() {
    state := ReadState()
    try
        return state["status"]
    catch
        return "IDLE"
}

; 检查是否可以买入（T+1限制）
CanBuyToday() {
    state := ReadState()
    today := FormatTime(, "yyyy-MM-dd")

    ; 如果今天卖出了，不能再买
    if (state["sell_today_flag"]) {
        return false
    }

    ; 如果当前有持仓，不能买
    if (state["status"] = "HOLDING") {
        return false
    }

    return true
}

; 设置持仓状态
SetHolding(stock_code, buy_price) {
    state := ReadState()
    state["status"] := "HOLDING"
    state["stock_code"] := stock_code
    state["buy_price"] := buy_price
    state["buy_date"] := FormatTime(, "yyyy-MM-dd")
    state["sell_today_flag"] := false
    WriteState(state)
}

; 设置清仓状态
SetIdle() {
    state := ReadState()
    state["status"] := "IDLE"
    state["sell_today_flag"] := true  ; 今天卖出了，次日才能买
    WriteState(state)
}

; 检查T+1是否解锁（每天开盘前调用）
CheckT1Unlock() {
    state := ReadState()
    today := FormatTime(, "yyyy-MM-dd")
    last_updated := SubStr(state["last_updated"], 1, 10)

    ; 如果上次更新不是今天，且有卖出标志，则清除
    if (last_updated != today and state["sell_today_flag"]) {
        state["sell_today_flag"] := false
        WriteState(state)
        ShowTip("T+1 已解锁，今日可重新选股")
    }
}

; 获取持仓信息
GetHoldingInfo() {
    state := ReadState()
    if (state["status"] = "HOLDING") {
        return {stock_code: state["stock_code"], buy_price: state["buy_price"], buy_date: state["buy_date"]}
    }
    return ""
}

; ============================================================
; 热键测试
; ============================================================
^+r::RunStockSelection()    ; Ctrl+Shift+R 测试选股
^+b::AutoBuy()              ; Ctrl+Shift+B 测试买入
^+s::RunMacdMonitor()       ; Ctrl+Shift+S 测试监控
^+t::ShowState()            ; Ctrl+Shift+T 显示当前状态

; 显示当前状态
ShowState() {
    state := ReadState()
    today := FormatTime(, "yyyy-MM-dd")
    msg := "当前状态: " . state["status"] . "`n"
    msg .= "持仓股票: " . (state["stock_code"] ? state["stock_code"] : "无") . "`n"
    msg .= "买入价格: " . (state["buy_price"] ? state["buy_price"] : "N/A") . "`n"
    msg .= "买入日期: " . (state["buy_date"] ? state["buy_date"] : "N/A") . "`n"
    msg .= "今日卖出: " . (state["sell_today_flag"] ? "是 (T+1锁定)" : "否") . "`n"
    msg .= "可买入: " . (CanBuyToday() ? "是" : "否 (T+1限制或已有持仓)")
    MsgBox msg, "交易状态", "Iconi"
}

; ============================================================
; 定时器系统：使用 SetTimer 和 CheckTimer
; ============================================================

; 检查是否可以执行定时任务
CheckTimer() {
    ; 周末不交易
    if (A_WDay = 1 or A_WDay = 7)
        return false

;    ; 检查是否在交易时间内
    time_sec := A_Hour * 3600 + A_Min * 60 + A_Sec
    trading_start := 9 * 3600 + 15 * 60
    trading_end := 15 * 3600 + 5 * 60

    return (time_sec >= trading_start and time_sec <= trading_end)
}

; 检查是否到达指定时间（精确到分钟）
IsTimeReached(target_hour, target_min) {
    return (A_Hour = target_hour and A_Min = target_min)
}

; 9:20 选股定时器
Timer920() {
    if (!CheckTimer() or !IsTimeReached(15, 13))
        return

    current_status := GetCurrentStatus()
    if (current_status = "IDLE" and CanBuyToday()) {
        ShowTip("9:20 - 正在选股...")
        RunStockSelection()
    }
}

; 9:30 开盘价检查定时器
Timer930() {
    if (!CheckTimer() or !IsTimeReached(15, 15))
        return

    current_status := GetCurrentStatus()
    if (current_status = "SCAN_DONE") {
        ShowTip("9:30 - 检查开盘价偏离...")
        CheckOpenPrice()
    }
}

; 9:31 自动买入定时器
Timer931() {
    if (!CheckTimer() or !IsTimeReached(15, 06))
        return

    current_status := GetCurrentStatus()
    if (current_status = "WAIT_BUY") {
        ShowTip("9:31 - 自动买入...")
        AutoBuy()
    }
}

; 14:55 MACD监控定时器
Timer1455() {
    if !IsTimeReached(15, 33)
        return

    current_status := GetCurrentStatus()
    if (current_status = "HOLDING") {
        ShowTip("14:55 - 运行MACD监控...")
        RunMacdMonitor()
    }
}

; 15:05 收盘检查定时器
Timer1505() {
    if (!CheckTimer() or !IsTimeReached(15, 5))
        return

    PostCloseCheck()
}

; 启动所有定时器（每60s检查一次）
SetTimer Timer920, 60000
SetTimer Timer930, 60000
SetTimer Timer931, 60000
SetTimer Timer1455, 60000
SetTimer Timer1505, 60000


; ============================================================
; 子程序（v2 函数风格）
; ============================================================

RunStockSelection() {
    global BUY_SIGNAL, SIGNAL_FILE, PYTHON_PATH, SCANNER_SCRIPT

    ShowTip("正在运行选股脚本...")

    ; 运行选股脚本
    RunWait '"' . PYTHON_PATH . '" "' . SCANNER_SCRIPT . '"'

    if (!FileExist(BUY_SIGNAL)) {
        ShowTip("今日无信号股")
        state := ReadState()
        ; 保持IDLE状态，不改变
        ShowTip("选股完成: 无信号")
        return
    }

    ; 读取最优信号
    code := ""
    price := 0
    content := FileRead(BUY_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if (InStr(A_LoopField, "#") or A_LoopField = "")
            continue
        fields := StrSplit(A_LoopField, "|")
        if (fields.Length >= 2) {
            code := fields[2]
            if (fields.Length >= 3)
                price := Number(fields[3])
            break
        }
    }

    if (code = "") {
        ShowTip("未找到有效信号")
        return
    }

    ; 状态改为 SCAN_DONE（等待开盘价检查）
    state := ReadState()
    state["status"] := "SCAN_DONE"
    state["scan_stock_code"] := code
    state["scan_price"] := price
    WriteState(state)
    
    ShowTip("选股完成: " . code)
}


CheckOpenPrice() {
    global SIGNAL_FILE, PYTHON_PATH, CHECK_OPEN_SCRIPT

    TrayTip ("MACD 自动交易", "正在检查开盘价偏离...", 10, 1)

    RunWait '"' . PYTHON_PATH . '" "' . CHECK_OPEN_SCRIPT . '"', , "Hide"

    deviation := ""
    if (FileExist(SIGNAL_FILE)) {
        content := FileRead(SIGNAL_FILE)
        Loop Parse, content, "`n", "`r" {
            if (InStr(A_LoopField, "开盘偏离:")) {
                deviation := StrReplace(A_LoopField, "开盘偏离:")
                deviation := Trim(deviation)
                if (InStr(deviation, "%"))
                    deviation := StrReplace(deviation, "%")
            }
        }
    }

    deviation_val := Number(deviation = "" ? 0 : deviation)

    if (deviation_val > 3) {
        TrayTip ("MACD 自动交易", "开盘偏离 " . deviation . "，超过3%，放弃本次信号", 15, 1)
        ShowTip("偏离过大: " . deviation)
        ; 重置状态
        state := ReadState()
        state["scan_stock_code"] := ""
        state["scan_price"] := 0
        WriteState(state)
        return
    }

    ; 状态改为 WAIT_BUY（等待买入）
    state := ReadState()
    state["status"] := "WAIT_BUY"
    WriteState(state)
    
    ShowTip("开盘价正常，将在9:31自动买入")
}


AutoBuy() {
    global BUY_SIGNAL, PYTHON_PATH
    global STOCK_CODE_X, STOCK_CODE_Y, SHARES_X, SHARES_Y, BUY_BTN_X, BUY_BTN_Y
    global INSURE_X, INSURE_Y, CLOSE_WIN_X, CLOSE_WIN_Y

    state := ReadState()
    if (state["status"] != "WAIT_BUY") {
        ShowTip("状态异常（非待买入状态），跳过买入")
        return
    }

    code := state["scan_stock_code"]
    price := state["scan_price"]

    ; 跳转到东方财富模拟盘
    ShowTip("正在下单: " . code)
    if (!JumpToEastMoney())
        return

    ; 填入股票代码（去掉 .SH/.SZ 后缀）
    code_clean := StripCodeSuffix(code)
    MouseMove STOCK_CODE_X, STOCK_CODE_Y, 10
    Click
    Send "^a{Del}" . code_clean
    Sleep 500

    ; 填入数量 100 股
    MouseMove SHARES_X, SHARES_Y, 10
    Click
    Send "^a{Del}100"
    Sleep 1000

    ; 点击买入按钮
    MouseMove BUY_BTN_X, BUY_BTN_Y, 10
    Click
    Sleep 1000

    ; 点击确认按钮
    MouseMove INSURE_X, INSURE_Y, 10
    Click
    Sleep 2000

    ; 关闭窗口
    MouseMove CLOSE_WIN_X, CLOSE_WIN_Y, 10
    Click

    ; 设置持仓状态
    SetHolding(code, price)
    
    TrayTip ("MACD 自动交易", "已自动买入 " . code . "`n系统将在14:55自动监控", 15, 1)
    SoundBeep 1000, 300
    ShowTip("已买入: " . code)
}


RunMacdMonitor() {
    global SELL_SIGNAL, PYTHON_PATH, MONITOR_SCRIPT
    global SHARES_X, SHARES_Y, SELL_BTN_X, SELL_BTN_Y
    global INSURE_X, INSURE_Y, CLOSE_WIN_X, CLOSE_WIN_Y

    ShowTip("正在运行MACD监控...")

    ; 获取持仓信息
    holding := GetHoldingInfo()
    if (!holding) {
        ShowTip("没有持仓，跳过监控")
        return
    }
    
    ; 运行监控脚本（传入股票代码和买入价格）
    cmd := '"' . PYTHON_PATH . '" "' . MONITOR_SCRIPT . '" --stock ' . holding.stock_code . ' --buy-price ' . holding.buy_price
    RunWait cmd, , "Hide"

    if (!FileExist(SELL_SIGNAL)) {
        ShowTip("MACD未下降，继续持有")
        TrayTip ("MACD 自动交易", "MACD未下降，继续持有，明日检查是否卖出", 10, 1)
        return
    }

    ; 读取卖出信号
    code := ""
    reason := ""
    content := FileRead(SELL_SIGNAL)
    Loop Parse, content, "`n", "`r" {
        if (A_Index = 1) {
            fields := StrSplit(A_LoopField, "|")
            code := fields[1]
        }
        if (InStr(A_LoopField, "原因:"))
            reason := StrReplace(A_LoopField, "原因:")
    }

    ShowTip("触发卖出: " . code)

    ; 自动执行卖出
    JumpToEastMoney()

    ; 点击委托卖出
    MouseMove DEPUTE_SELL_X, DEPUTE_SELL_Y, 10
    Click
    sleep 1000

    ; 填入卖出数量（不填股票代码，卖出界面已有代码）
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
    Sleep 2000

    ; 关闭窗口
    MouseMove CLOSE_WIN_X, CLOSE_WIN_Y, 10
    Click

    ; 设置为空仓状态（带T+1标记）
    SetIdle()
    
    TrayTip ("MACD 自动交易", "已自动卖出 " . code . "`n原因: " . reason . "`nT+1限制，明日才能重新选股", 15, 1)
    SoundBeep 800, 500
    ShowTip("已卖出: " . code)
}


PostCloseCheck() {
    global PYTHON_PATH
    
    ; 检查T+1是否需要解锁
    CheckT1Unlock()
    
    state := ReadState()
    TrayTip ("MACD 自动交易", "收盘检查完成`n当前状态: " . state["status"], 10, 1)
}


; 检查东方财富窗口是否存在
CheckEastMoneyWindow() {
    if !WinExist("ahk_exe mainfree.exe") {
        MsgBox "未找到东方财富窗口", "错误", "IconX"
        return false
    }
    WinActivate
    Sleep 500
    return true
}


; 去掉股票代码的后缀（如 .SH .SZ .sh .sz），只保留纯代码
StripCodeSuffix(code) {
    code := RegExReplace(code, "i)\.(SH|SZ)$", "")
    return Trim(code)
}

JumpToEastMoney() {
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
    TrayTip ("MACD 自动交易", msg, 10, 1)
    ToolTip msg, 0, 0
    SetTimer RemoveTip, -3000
}


RemoveTip() {
    ToolTip
}


; ============================================================
; 托盘菜单 (v2)
; ============================================================
Tray := A_TrayMenu
Tray.Delete()
Tray.Add("查看状态", ShowStateMenu)
Tray.Add
Tray.Add("立即选股", RunStockSelectionMenu)
Tray.Add("立即买入检查", CheckOpenPriceMenu)
Tray.Add("立即买入", AutoBuyMenu)
Tray.Add("立即监控", RunMacdMonitorMenu)
Tray.Add
Tray.Add("暂停自动交易", ToggleAutoMenu)
Tray.Add
Tray.Add("查看日志", OpenLogMenu)
Tray.Add("退出", ExitAppMenu)
Tray.Default := "立即选股"
Tray.ClickCount := 1
Tray.Tip := "MACD 全自动交易助手`n自动运行中..."

TrayTip ("MACD 全自动交易助手", "已启动`n全自动交易运行中`n请保持网络畅通", 10, 1)

; 托盘菜单回调函数
ShowStateMenu(ItemName, ItemPos, Menu) {
    ShowState()
}

RunStockSelectionMenu(ItemName, ItemPos, Menu) {
    RunStockSelection()
}

CheckOpenPriceMenu(ItemName, ItemPos, Menu) {
    CheckOpenPrice()
}

AutoBuyMenu(ItemName, ItemPos, Menu) {
    AutoBuy()
}

RunMacdMonitorMenu(ItemName, ItemPos, Menu) {
    RunMacdMonitor()
}

ToggleAutoMenu(ItemName, ItemPos, Menu) {
    ToggleAuto()
}

OpenLogMenu(ItemName, ItemPos, Menu) {
    OpenLog()
}

ExitAppMenu(ItemName, ItemPos, Menu) {
    ExitApp()
}

ToggleAuto() {
    global AUTO_MODE
    if (AUTO_MODE) {
        AUTO_MODE := false
        TrayTip ("MACD", "自动交易已暂停", 10, 1)
    } else {
        AUTO_MODE := true
        TrayTip ("MACD", "自动交易已恢复", 10, 1)
    }
}

OpenLog() {
    log_file := "C:\Users\35223\MACD\MACD_Stock_Strategy\scanner_log.txt"
    if (FileExist(log_file))
        Run "notepad.exe `"" . log_file . "`""
    else
        MsgBox "日志文件不存在", "提示"
}

; ============================================================
; JSON 库（简化版，用于解析/生成JSON）
; ============================================================
class Json {
    static Load(str) {
        ; 简单JSON解析器
        result := Map()
        str := Trim(str)

        ; 处理空字符串或无效JSON
        if (str = "" or str = "{}" or str = "{") {
            result["status"] := "IDLE"
            result["stock_code"] := ""
            result["buy_date"] := ""
            result["buy_price"] := 0
            result["sell_today_flag"] := false
            result["last_updated"] := ""
            return result
        }

        if (SubStr(str, 1, 1) = "{")
            str := SubStr(str, 2, -1)

        Loop Parse, str, "," {
            pair := StrSplit(Trim(A_LoopField), ":",, 2)
            if (pair.Length >= 2) {
                key := Trim(pair[1])
                val := Trim(pair[2])

                ; 去除引号
                if (SubStr(key, 1, 1) = Chr(34))
                    key := SubStr(key, 2, -1)
                if (SubStr(val, 1, 1) = Chr(34)) {
                    val := SubStr(val, 2, -1)
                } else if (val = "true") {
                    val := true
                } else if (val = "false") {
                    val := false
                } else if (val = "null") {
                    val := ""
                } else {
                    val := Number(val)
                }

                result[key] := val
            }
        }
        return result
    }
    
    static Stringify(obj) {
        ; 简单JSON生成器
        parts := []
        for key, val in obj {
            if (val = "") {
                parts.Push('"' . key . '":null')
            } else if (val = true or val = false) {
                parts.Push('"' . key . '":' . (val ? "true" : "false"))
            } else if (val is Integer or val is Float) {
                parts.Push('"' . key . '":' . val)
            } else {
                parts.Push('"' . key . '":"' . val . '"')
            }
        }
        result := ""
        for i, part in parts {
            result .= (i > 1 ? "," : "") . part
        }
        return "{" . result . "}"
    }
}
