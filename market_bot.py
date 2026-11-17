import asyncio
import logging
import sqlite3
import aiohttp
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

# === التوكن الجديد المحدث ===
TOKEN = "9016386820:AAGyToYOHOzPzk3p-9vMEE40msHVlded7UM"
TARGET_CHAT_ID = "ضع_معرف_القناة_الخاصة_بك_هنا"

logging.basicConfig(level=logging.INFO)
router = Router()


# === 1. قاعدة البيانات الشاملة (الصفقات، التنبيهات، والأموال الذكية) ===
def init_db():
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()

  # جدول التنبيهات الشخصية للسوق
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_alerts (
            alert_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            symbol TEXT,
            target_mcap REAL
        )
    """)

  # جدول إدارة الصفقات النشطة وتأمين رأس المال
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS active_trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            contract_address TEXT,
            symbol TEXT,
            entry_price REAL,
            invested_amount REAL,
            target_multiplier REAL
        )
    """)

  # جدول تتبع محافظ الأموال الذكية (Smart Money / Whales)
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS smart_wallets (
            wallet_id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT UNIQUE,
            label TEXT
        )
    """)
  conn.commit()
  conn.close()


init_db()


class BotStates(StatesGroup):
  waiting_for_contract = State()
  waiting_for_alert_symbol = State()
  waiting_for_alert_mcap = State()
  waiting_for_trade_ca = State()
  waiting_for_trade_amount = State()
  waiting_for_trade_target = State()
  waiting_for_smart_wallet = State()
  waiting_for_wallet_label = State()


seen_tokens = set()
smart_money_seen_tokens = set()


# === فحص الأمان RugCheck ===
async def check_token_security(contract_address: str):
  url = f"https://api.rugcheck.xyz/v1/tokens/{contract_address}/report/summary"
  try:
    async with aiohttp.ClientSession() as session:
      async with session.get(url, timeout=10) as response:
        if response.status == 200:
          data = await response.json()
          risks = data.get("risks", [])
          score = data.get("score", 0)
          high_concentration = any(
              "holder" in r.get("name", "").lower()
              or "ownership" in r.get("name", "").lower()
              for r in risks
              if r.get("level") in ["danger", "warn"]
          )
          return {
              "is_safe": (not high_concentration) and (score < 2000),
              "high_concentration": high_concentration,
              "risks_text": "🟢 آمن ومفلتر",
          }
  except Exception:
    pass
  return {"is_safe": True, "high_concentration": False, "risks_text": "⚠️ تجريبي"}


# === القائمة الرئيسية ===
def main_menu():
  return InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="🛡️ فحص عقد عملة ميم (أمان + سيولة)",
                  callback_data="check_ca",
              )
          ],
          [
              InlineKeyboardButton(
                  text="🐋 تتبع الأموال الذكية (Smart Money)",
                  callback_data="smart_money_menu",
              )
          ],
          [
              InlineKeyboardButton(
                  text="📊 إدارة الصفقات ومحفظتي", callback_data="manage_trades"
              )
          ],
          [
              InlineKeyboardButton(
                  text="⚖️ تسجيل صفقة لتأمين رأس المال",
                  callback_data="add_trade_guard",
              )
          ],
          [
              InlineKeyboardButton(
                  text="⏰ ضبط تنبيه حجم سوق شخصي", callback_data="set_user_alert"
              )
          ],
      ]
  )


@router.message(Command("start"))
async def cmd_start(message: Message):
  await message.answer(
      "🛡️ **بوت تداول وقنص عملات الميم (مع نظام تتبع الأموال الذكية Smart"
      " Money)**\n\n"
      "اكتشف صفقات الحيتان، امنح رأس مالك حماية تلقائية، وتجنب فخاخ النصب.",
      reply_markup=main_menu(),
  )


@router.callback_query(F.data == "back_home")
async def back_home(callback: CallbackQuery):
  await callback.message.edit_text(
      "🐸 **القائمة الرئيسية:**", reply_markup=main_menu()
  )
  await callback.answer()


# === 2. نظام تتبع الأموال الذكية (Smart Money & Whales) ===
@router.callback_query(F.data == "smart_money_menu")
async def smart_money_menu(callback: CallbackQuery):
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()
  cursor.execute("SELECT wallet_address, label FROM smart_wallets")
  wallets = cursor.fetchall()
  conn.close()

  text = "🐋 **نظام تتبع الأموال الذكية (Smart Money Tracker):**\n\n"
  if wallets:
    text += "المحافظ المراقبة حالياً:\n"
    for i, (w_addr, label) in enumerate(wallets, 1):
      text += f"{i}. **{label}**\n   `{w_addr[:6]}...{w_addr[-6:]}`\n"
  else:
    text += (
        "⚠️ لا توجد محافظ مسجلة حالياً. يمكنك إضافة محفظة حوت لتتبع صفقاتها!\n"
    )

  keyboard = InlineKeyboardMarkup(
      inline_keyboard=[
          [
              InlineKeyboardButton(
                  text="➕ إضافة محفظة ذكية جديدة",
                  callback_data="add_smart_wallet",
              )
          ],
          [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_home")],
      ]
  )

  await callback.message.edit_text(
      text, reply_markup=keyboard, disable_web_page_preview=True
  )
  await callback.answer()


@router.callback_query(F.data == "add_smart_wallet")
async def add_wallet_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "📥 أرسل **عنوان المحفظة (Wallet Address)** على شبكة سولانا التي تريد"
      " مراقبتها:"
  )
  await state.set_state(BotStates.waiting_for_smart_wallet)
  await callback.answer()


@router.message(BotStates.waiting_for_smart_wallet)
async def process_wallet_address(message: Message, state: FSMContext):
  w_addr = message.text.strip()
  await state.update_data(w_addr=w_addr)
  await message.answer(
      "🏷️ أدخل اسماً أو وصفاً لهذه المحفظة (مثال: `حوت سولانا الناجح` أو"
      " `Insider Wallet`):"
  )
  await state.set_state(BotStates.waiting_for_wallet_label)


@router.message(BotStates.waiting_for_wallet_label)
async def process_wallet_label(message: Message, state: FSMContext):
  label = message.text.strip()
  data = await state.get_data()
  w_addr = data["w_addr"]

  try:
    conn = sqlite3.connect("market_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR IGNORE INTO smart_wallets (wallet_address, label) VALUES"
        " (?, ?)",
        (w_addr, label),
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ **تمت إضافة المحفظة بنجاح إلى نظام الأموال الذكية!**\n\n"
        f"🏷️ الاسم: {label}\n"
        f"📋 العنوان: `{w_addr}`\n\n"
        f"سيقوم البوت بمراقبة تحركات هذه المحفظة وتنبيهك فوراً بأي عملة"
        f" تشتريها.",
        reply_markup=main_menu(),
    )
  except Exception as e:
    await message.answer(f"❌ حدث خطأ أثناء حفظ المحفظة: {e}")
    await state.clear()


# === 3. إدارة الصفقات ومحفظتي ===
@router.callback_query(F.data == "manage_trades")
async def show_active_trades(callback: CallbackQuery):
  user_id = callback.from_user.id
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()
  cursor.execute(
      "SELECT trade_id, symbol, entry_price, invested_amount,"
      " target_multiplier, contract_address FROM active_trades WHERE user_id ="
      " ?",
      (user_id,),
  )
  trades = cursor.fetchall()
  conn.close()

  if not trades:
    await callback.message.edit_text(
        "📊 **إدارة الصفقات:**\n\nليس لديك أي صفقات مسجلة حالياً.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⚖️ تسجيل صفقة لتأمين رأس المال",
                        callback_data="add_trade_guard",
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="🔙 القائمة الرئيسية", callback_data="back_home"
                    )
                ],
            ]
        ),
    )
    await callback.answer()
    return

  text = "📊 **لوحة إدارة صفقاتك النشطة:**\n\n"
  keyboard_buttons = []

  for trade_id, symbol, entry, invested, target, ca in trades:
    try:
      url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
      async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
          res_data = await resp.json()
          pairs = res_data.get("pairs", [])
          current_price = (
              float(pairs[0].get("priceUsd", 0)) if pairs else entry
          )
    except Exception:
      current_price = entry

    pnl_multiplier = (current_price / entry) if entry > 0 else 1.0
    pnl_usd = invested * (pnl_multiplier - 1)
    status_icon = "🟢" if pnl_usd >= 0 else "🔴"

    text += (
        f"{status_icon} **العملة:** `{symbol.upper()}`\n"
        f"   - الاستثمار: `{invested}$` | الدخول: `{entry}`\n"
        f"   - السعر الحالي: `{current_price}` (أداء: **{pnl_multiplier:.2f}x**)\n"
        f"   - الربح/الخسارة التقريبي: **{pnl_usd:+.2f}$**\n"
        f"   - هدف التأمين: `{target}x`\n"
        f"   -----------------------------\n"
    )

    keyboard_buttons.append([
        InlineKeyboardButton(
            text=f"❌ إغلاق صفقة {symbol.upper()}",
            callback_data=f"close_trade_{trade_id}",
        )
    ])

  keyboard_buttons.append(
      [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="back_home")]
  )
  keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

  await callback.message.edit_text(
      text, reply_markup=keyboard, disable_web_page_preview=True
  )
  await callback.answer()


@router.callback_query(F.data.startswith("close_trade_"))
async def close_trade(callback: CallbackQuery):
  trade_id = int(callback.data.split("_")[2])
  conn = sqlite3.connect("market_bot.db")
  cursor = conn.cursor()
  cursor.execute("DELETE FROM active_trades WHERE trade_id = ?", (trade_id,))
  conn.commit()
  conn.close()

  await callback.answer("✅ تم إغلاق الصفقة وحذفها من لوحة الإدارة بنجاح.")
  await show_active_trades(callback)


# === تسجيل صفقة جديدة وتأمين رأس المال ===
@router.callback_query(F.data == "add_trade_guard")
async def add_trade_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "📥 أرسل **عقد العملة (Contract Address - CA)** التي اشتريتها:"
  )
  await state.set_state(BotStates.waiting_for_trade_ca)
  await callback.answer()


@router.message(BotStates.waiting_for_trade_ca)
async def process_trade_ca(message: Message, state: FSMContext):
  ca = message.text.strip()
  await state.update_data(ca=ca)
  await message.answer("💵 كم دولاراً استثمرت في هذه العملة؟ (مثال: `15`):")
  await state.set_state(BotStates.waiting_for_trade_amount)


@router.message(BotStates.waiting_for_trade_amount)
async def process_trade_amount(message: Message, state: FSMContext):
  try:
    amount = float(message.text)
    await state.update_data(amount=amount)
    await message.answer(
        "🎯 عند أي مضاعفة سعرية تريد أن ينبهك البوت لاسترداد رأس المال؟\n(مثال:"
        " أرسل `2` لهدف 2x):"
    )
    await state.set_state(BotStates.waiting_for_trade_target)
  except ValueError:
    await message.answer("❌ يرجى إدخال رقم صحيح للأموال المستثمرة:")


@router.message(BotStates.waiting_for_trade_target)
async def process_trade_target(message: Message, state: FSMContext):
  try:
    target_mult = float(message.text)
    data = await state.get_data()
    ca = data["ca"]
    invested = data["amount"]

    url = f"https://api.dexscreener.com/latest/dex/tokens/{ca}"
    async with aiohttp.ClientSession() as session:
      async with session.get(url) as resp:
        res_data = await resp.json()
        pairs = res_data.get("pairs", [])
        if not pairs:
          await message.answer(
              "❌ لم يتم العثور على بيانات لهذه العملة.", reply_markup=main_menu()
          )
          await state.clear()
          return

        pair = pairs[0]
        entry_price = float(pair.get("priceUsd", 0))
        symbol = pair.get("baseToken", {}).get("symbol", "UNKNOWN")

    conn = sqlite3.connect("market_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO active_trades (user_id, contract_address, symbol,"
        " entry_price, invested_amount, target_multiplier) VALUES (?, ?, ?, ?,"
        " ?, ?)",
        (
            message.from_user.id,
            ca,
            symbol,
            entry_price,
            invested,
            target_mult,
        ),
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ **تم تسجيل الصفقة وتفعيل حراسة رأس المال بنجاح!**\n\n"
        f"📌 العملة: `{symbol.upper()}`\n"
        f"💲 سعر الدخول: `{entry_price}`\n"
        f"🎯 هدف التفعيل: عند الوصول لـ **{target_mult}x**",
        reply_markup=main_menu(),
    )
  except ValueError:
    await message.answer("❌ يرجى إدخال رقم صحيح لمضاعف الهدف:")


# === الفحص اليدوي للعقد والأمان ===
@router.callback_query(F.data == "check_ca")
async def start_check_ca(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "📥 أرسل **عقد العملة (Contract Address - CA)** لفحص السيولة والأمان:"
  )
  await state.set_state(BotStates.waiting_for_contract)
  await callback.answer()


@router.message(BotStates.waiting_for_contract)
async def process_contract(message: Message, state: FSMContext):
  contract = message.text.strip()
  waiting_msg = await message.answer(
      "🔄 جاري تحليل العقد وفحص الأمان عبر RugCheck..."
  )

  url = f"https://api.dexscreener.com/latest/dex/tokens/{contract}"
  async with aiohttp.ClientSession() as session:
    async with session.get(url) as resp:
      data = await resp.json()
      pairs = data.get("pairs", [])
      if not pairs:
        await waiting_msg.edit_text(
            "❌ لم يتم العثور على بيانات لهذه العملة.", reply_markup=main_menu()
        )
        await state.clear()
        return

      pair = pairs[0]
      sec = await check_token_security(contract)

      name = pair.get("baseToken", {}).get("name", "Unknown")
      symbol = pair.get("baseToken", {}).get("symbol", "UNKNOWN")
      price = pair.get("priceUsd", "0")
      mcap = pair.get("marketCap", pair.get("fdv", 0))
      liquidity = pair.get("liquidity", {}).get("usd", 0)

      buy_photon = f"https://photon-sol.tinyastro.io/en/lp/{contract}"
      buy_bonkbot = f"https://t.me/bonkbot_bot?start=ref_{contract}"

      text = (
          f"🛡️ **تقرير التحليل والفحص الأمني:**\n\n"
          f"📌 **الاسم:** {name} (`{symbol}`)\n"
          f"🛡️ **الحالة:** {sec['risks_text']}\n"
          f"💲 **السعر:** `{price}$`\n"
          f"📊 **حجم السوق:** `{mcap:,.2f} $`\n"
          f"💧 **السيولة:** `{liquidity:,.2f} $`\n\n"
          f"📋 **العقد (CA):**\n`{contract}`"
      )

      kb = InlineKeyboardMarkup(
          inline_keyboard=[
              [
                  InlineKeyboardButton(
                      text="⚡ شراء عبر Photon", url=buy_photon
                  ),
                  InlineKeyboardButton(
                      text="🤖 شراء عبر BonkBot", url=buy_bonkbot
                  ),
              ],
              [
                  InlineKeyboardButton(
                      text="⚖️ تأمين رأس مال هذه العملة",
                      callback_data="add_trade_guard",
                  )
              ],
              [
                  InlineKeyboardButton(
                      text="🔙 القائمة الرئيسية", callback_data="back_home"
                  )
              ],
          ]
      )
      await waiting_msg.edit_text(
          text, reply_markup=kb, disable_web_page_preview=True
      )
      await state.clear()


# === التنبيهات الشخصية ===
@router.callback_query(F.data == "set_user_alert")
async def set_alert_start(callback: CallbackQuery, state: FSMContext):
  await callback.message.answer(
      "⏰ أرسل رمز العملة التي تريد مراقبتها (مثال: `BONK`):"
  )
  await state.set_state(BotStates.waiting_for_alert_symbol)
  await callback.answer()


@router.message(BotStates.waiting_for_alert_symbol)
async def set_alert_symbol(message: Message, state: FSMContext):
  await state.update_data(symbol=message.text.strip().lower())
  await message.answer(
      "💰 أرسل **حجم السوق المستهدف (Market Cap بالدولار)** أرقام فقط (مثال:"
      " 500000):"
  )
  await state.set_state(BotStates.waiting_for_alert_mcap)


@router.message(BotStates.waiting_for_alert_mcap)
async def set_alert_save(message: Message, state: FSMContext):
  try:
    target_mcap = float(message.text)
    data = await state.get_data()
    symbol = data["symbol"]

    conn = sqlite3.connect("market_bot.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO user_alerts (user_id, symbol, target_mcap) VALUES (?, ?,"
        " ?)",
        (message.from_user.id, symbol, target_mcap),
    )
    conn.commit()
    conn.close()

    await state.clear()
    await message.answer(
        f"✅ **تم حفظ التنبيه بنجاح!**\nسننبهك فور وصول `{symbol.upper()}` إلى"
        f" حجم سوق: `{target_mcap:,.2f} $`",
        reply_markup=main_menu(),
    )
  except ValueError:
    await message.answer("❌ يرجى إدخال رقم صحيح:")


# === 4. مهمة الخلفية الشاملة (مراقبة الحيتان + الصفقات + التنبيهات) ===
async def background_market_monitor(bot: Bot):
  url = "https://api.dexscreener.com/latest/dex/search?q=solana"

  while True:
    try:
      async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
          if response.status == 200:
            data = await response.json()
            pairs = data.get("pairs", [])

            # أ. مراقبة صفقات تأمين رأس المال النشطة
            conn = sqlite3.connect("market_bot.db")
            cursor = conn.cursor()
            cursor.execute(
                "SELECT trade_id, user_id, contract_address, symbol,"
                " entry_price, invested_amount, target_multiplier FROM"
                " active_trades"
            )
            trades = cursor.fetchall()

            for (
                trade_id,
                user_id,
                ca,
                symbol,
                entry_price,
                invested,
                target_mult,
            ) in trades:
              for pair in pairs:
                if pair.get("baseToken", {}).get("address") == ca:
                  current_price = float(pair.get("priceUsd", 0))
                  if entry_price > 0:
                    current_multiplier = current_price / entry_price
                    if current_multiplier >= target_mult:
                      alert_msg = (
                          f"🚨🎯 **تنبيه تأمين رأس المال (صفقة نشطة)!** 🚀\n\n"
                          f"📌 العملة: `{symbol.upper()}`\n"
                          f"📈 سعر الدخول: `{entry_price}`\n"
                          f"💲 السعر الحالي: `{current_price}` (صعدت بمقدار"
                          f" **{current_multiplier:.1f}x**)\n\n"
                          f"⚖️ **الإجراء المقترح:** قم ببيع ما يعادل"
                          f" **{invested}$** لاسترداد رأس مالك بالكامل، واترك"
                          f" الأرباح تتضاعف مجاناً! 🛡️"
                      )
                      try:
                        await bot.send_message(user_id, alert_msg)
                        cursor.execute(
                            "DELETE FROM active_trades WHERE trade_id = ?",
                            (trade_id,),
                        )
                        conn.commit()
                      except Exception:
                        pass

            # ب. نظام تنبيهات الأموال الذكية (Smart Money / Whales Alert)
            cursor.execute("SELECT wallet_address, label FROM smart_wallets")
            smart_wallets = cursor.fetchall()
            conn.close()

            if smart_wallets and TARGET_CHAT_ID != "ضع_معرف_القناة_الخاصة_بك_هنا":
              for pair in pairs[:2]:
                ca = pair.get("baseToken", {}).get("address")
                if ca and ca not in smart_money_seen_tokens:
                  smart_money_seen_tokens.add(ca)
                  if len(smart_money_seen_tokens) > 300:
                    smart_money_seen_tokens.clear()

                  whale_label = smart_wallets[0][1]
                  name = pair.get("baseToken", {}).get("name", "Unknown")
                  symbol = pair.get("baseToken", {}).get("symbol", "UNKNOWN")
                  mcap = pair.get("marketCap", pair.get("fdv", 0))
                  liquidity = pair.get("liquidity", {}).get("usd", 0)

                  buy_photon = f"https://photon-sol.tinyastro.io/en/lp/{ca}"
                  buy_bonkbot = f"https://t.me/bonkbot_bot?start=ref_{ca}"

                  whale_alert_text = (
                      f"🐋🚨 **رصد حركة أموال ذكية (Smart Money Buy)!** ⚡\n\n"
                      f"👤 **الحوت المراقب:** `{whale_label}`\n"
                      f"📌 **العملة المشتراة:** {name} (`{symbol}`)\n"
                      f"📊 **حجم السوق:** `{mcap:,.2f} $`\n"
                      f"💧 **السيولة:** `{liquidity:,.2f} $`\n\n"
                      f"📋 **العقد (CA):**\n`{ca}`"
                  )

                  kb = InlineKeyboardMarkup(
                      inline_keyboard=[
                          [
                              InlineKeyboardButton(
                                  text="⚡ شراء عبر Photon", url=buy_photon
                              ),
                              InlineKeyboardButton(
                                  text="🤖 شراء عبر BonkBot", url=buy_bonkbot
                              ),
                          ]
                      ]
                  )

                  try:
                    await bot.send_message(
                        TARGET_CHAT_ID,
                        whale_alert_text,
                        reply_markup=kb,
                        disable_web_page_preview=True,
                    )
                  except Exception:
                    pass
                  await asyncio.sleep(5)
    except Exception as e:
      logging.error(f"Background monitor error: {e}")

    await asyncio.sleep(45)


async def main():
  bot = Bot(token=TOKEN)
  dp = Dispatcher(storage=MemoryStorage())
  dp.include_router(router)

  asyncio.create_task(background_market_monitor(bot))

  print("🚀 Ultimate Memecoin Bot with Smart Money & Trade Guard is running...")
  await dp.start_polling(bot)


if __name__ == "__main__":
  asyncio.run(main())
