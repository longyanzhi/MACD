#Requires AutoHotkey v2.0
#SingleInstance Force

; ===== 可修改参数 =====
; 买入参数
buyStockCode := "600000"   ; 买入股票代码
buySharesCount := 100      ; 买入数量

; 卖出参数
sellSharesCount := 100     ; 卖出数量（卖出不需要代码）

; ===== 坐标 =====
stockCodeX := 255          ; 股票代码输入框
stockCodeY := 792
sharesX := 259             ; 数量输入框
sharesY := 910
buyButtonX := 293          ; 买入按钮
buyButtonY := 942
sellButtonX := 107         ; 卖出按钮
sellButtonY := 826

; ===== 热键 =====
; Ctrl+Shift+B 执行买入
^+b::DoBuy()

; Ctrl+Shift+S 执行卖出
^+s::DoSell()

; ===== 买入函数（需要填写代码+数量）=====
DoBuy() {
    if !WinExist("ahk_exe mainfree.exe") {
        MsgBox "未找到东方财富窗口", "错误", "IconX"
        return
    }
    WinActivate
    Sleep 500

    ; 填写股票代码
    MouseMove stockCodeX, stockCodeY, 100
    Click
    Send "^a{Del}"
    Send buyStockCode
    Sleep 500

    ; 填写买入数量
    MouseMove sharesX, sharesY, 10
    Click
    Send "^a{Del}"
    Send buySharesCount
    Sleep 200

    ; 点击买入按钮
    MouseMove buyButtonX, buyButtonY, 10
    Click

    TrayTip "交易完成", "已提交买入 " buyStockCode " x" buySharesCount, 2
}

; ===== 卖出函数（只填写数量，不填代码）=====
DoSell() {
    if !WinExist("ahk_exe mainfree.exe") {
        MsgBox "未找到东方财富窗口", "错误", "IconX"
        return
    }
    WinActivate
    Sleep 500

    ; 填写卖出数量（不填股票代码）
    MouseMove sharesX, sharesY, 10
    Click
    Send "^a{Del}"
    Send sellSharesCount
    Sleep 200

    ; 点击卖出按钮
    MouseMove sellButtonX, sellButtonY, 10
    Click

    TrayTip "交易完成", "已提交卖出 x" sellSharesCount, 2
}