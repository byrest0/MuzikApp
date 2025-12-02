# mymusics_fixed.py
# Düzeltilmiş MyMusics uygulaması - Flet 0.25+ uyumlu, Android APK amaçlı.
# Tasarıma mümkün olduğunca dokunulmadı. Ses ve overlay hataları giderildi.

import flet as ft
from youtube_search import YoutubeSearch
import yt_dlp
import json
import os
import threading
import time
import random
import re
import traceback

class MusicApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.app_running = True
        self.mobile_mode = True

        # 1. AYARLARI YÜKLE
        self.load_settings()
        self.setup_page()
        self.init_variables()

        # --- 2. SES MOTORU (DÜZELTİLDİ) ---
        # Audio görünür olarak eklenirse mobilde "Unknown control" veya overlay sorunu çıkabiliyor.
        # Bu yüzden kontrolü görünmez tutuyoruz, yine de çalışır durumda oluyor.
        try:
            self.audio_player = ft.Audio(
                src="",
                autoplay=False,
                volume=self.settings.get("volume", 1.0),
                on_position_changed=self.sure_guncelle,
                on_state_changed=self.audio_state_changed,
                visible=False,  # Görünmez yapıldı — ekranı kaplamaz
            )
            # Not: page.add yerine overlay'e eklemek gerekli olabilir; overlay'e ekliyoruz (görünmez).
            # Bazı Flet sürümlerinde kontrolün sayfada olması gerekiyor ki ses çalışsın.
            try:
                self.page.overlay.append(self.audio_player)
            except Exception:
                # overlay yoksa page.controls'a değil, doğrudan saklıyoruz (bazı ortamlarda overlay yok)
                try:
                    self.page.controls.append(self.audio_player)
                except Exception:
                    pass
        except Exception as e:
            print("Audio player oluşturulamadı:", e)
            self.audio_player = None

        # 3. ARAYÜZÜ OLUŞTUR
        self.build_ui()

        # 4. ARAYÜZÜ SAYFAYA EKLE
        # Başlangıçta keşfet view'ını ve nav bar'ı ekle
        try:
            self.page.add(self.view_kesfet)
            self.page.add(self.nav_bar)
        except Exception:
            # Eğer page.add hata verirse controls manipülasyonu ile ekle
            try:
                self.page.controls.insert(0, self.view_kesfet)
                self.page.controls.append(self.nav_bar)
            except: pass

        # Menüyü overlay'e ekle (BottomSheet)
        try:
            self.page.overlay.append(self.context_menu)
        except Exception:
            # fallback: nothing
            pass

        self.page.update()

        # 5. KONTROLLERİ AYARLA
        try:
            if hasattr(self, "ses_slider") and self.audio_player:
                self.ses_slider.value = self.audio_player.volume * 100
                self.page.update()
        except Exception:
            pass

        # 6. Başlangıç Verileri
        self.kesfet_kategori_getir("Rastgele")
        self.favorileri_listele()

        # Görselleştiriciyi başlat
        threading.Thread(target=self.visualizer_loop, daemon=True).start()


    def load_settings(self):
        self.settings_file = "ayarlar.json"
        self.settings = {"volume": 1.0, "shuffle": False, "repeat": False, "theme": "green"}
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    self.settings.update(json.load(f))
            except: pass

    def save_settings(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f)
        except: pass

    def setup_page(self):
        self.page.title = "MyMusics Mobile"
        self.page.theme_mode = "dark"
        self.page.bgcolor = "#000000"
        self.page.padding = 0
        self.page.scroll = None
        self.page.horizontal_alignment = "stretch"

        self.current_theme_color = self.settings["theme"]
        try:
            self.page.theme = ft.Theme(
                color_scheme_seed=self.current_theme_color,
                scrollbar_theme=ft.ScrollbarTheme(thickness=0)
            )
        except Exception:
            # Fallback: ignore theme issues
            pass

    def init_variables(self):
        self.favoriler_dosyasi = "favoriler.json"
        self.indirilenler_klasoru = "downloaded_songs"

        if not os.path.exists(self.indirilenler_klasoru):
            try: os.makedirs(self.indirilenler_klasoru)
            except: pass

        self.favori_listesi = []
        if os.path.exists(self.favoriler_dosyasi):
            try:
                with open(self.favoriler_dosyasi, "r", encoding="utf-8") as f:
                    content = f.read()
                    if content: self.favori_listesi = json.loads(content)
            except: self.favori_listesi = []

        self.caliniyor_mu = False
        self.oynatma_listesi = []
        self.gecmis_listesi = []
        self.suanki_index = -1

        self.shuffle_mode = self.settings.get("shuffle", False)
        self.repeat_mode = self.settings.get("repeat", False)

        self.is_slider_changing = False
        self.visualizer_active = True
        self.secilen_menu_sarkisi = None
        self.neon_colors = ["cyan", "magenta", "lime", "yellow", "orange", "#ff00ff", "#00ffff"]

    def build_ui(self):
        # Navigation bar
        self.nav_bar = ft.NavigationBar(
            selected_index=0,
            on_change=self.nav_degisti,
            bgcolor="#111111",
            destinations=[
                ft.NavigationBarDestination(icon="explore", label="Keşfet"),
                ft.NavigationBarDestination(icon="search", label="Ara"),
                ft.NavigationBarDestination(icon="library_music", label="Kitaplık"),
                ft.NavigationBarDestination(icon="play_circle_filled", label="Çalan"),
            ]
        )

        self.arama_kutusu = ft.TextField(
            hint_text="Şarkı veya sanatçı ara...",
            border_radius=25,
            bgcolor="#22ffffff",
            border_width=0,
            prefix_icon="search",
            content_padding=15,
            height=50,
            on_submit=self.arama_yap,
            text_size=16
        )

        self.kesfet_sonuclari = ft.ListView(expand=True, spacing=10, padding=10)
        self.arama_sonuclari = ft.ListView(expand=True, spacing=10, padding=10)
        self.favori_sonuclari = ft.ListView(expand=True, spacing=10, padding=10)

        # Visualizer bars
        self.visualizer_bars = []
        for _ in range(25):
            self.visualizer_bars.append(
                ft.Container(
                    width=6,
                    height=10,
                    bgcolor=self.current_theme_color,
                    border_radius=3,
                    animate=ft.Animation(300, "easeOut")
                )
            )

        self.visualizer_row = ft.Row(
            self.visualizer_bars,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=4,
            height=60,
            opacity=0
        )

        self.durum_yazisi = ft.Text("Müzik bekleniyor...", color="white54", size=12)
        self.suanki_sarki_adi = ft.Text("Seçim Yok", size=20, weight="bold", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, text_align="center")
        self.gecen_sure_txt = ft.Text("00:00", size=12, color="white54")
        self.toplam_sure_txt = ft.Text("00:00", size=12, color="white54")

        self.suanki_resim = ft.Image(
            src="https://upload.wikimedia.org/wikipedia/commons/1/14/No_Image_Available.jpg",
            width=340, height=340,
            fit=ft.ImageFit.COVER,
            border_radius=20,
            animate_scale=ft.Animation(400, "bounceOut")
        )

        self.loading_indicator = ft.ProgressRing(visible=False, color="white")
        self.resim_konteyner = ft.Container(
            content=ft.Stack([self.suanki_resim, ft.Container(content=self.loading_indicator, alignment=ft.alignment.center)], alignment=ft.alignment.center),
            shadow=ft.BoxShadow(blur_radius=30, color="black", spread_radius=2),
            border_radius=20,
            alignment=ft.alignment.center,
            padding=0,
            animate=ft.Animation(500, "easeOut")
        )

        # Player buttons
        self.play_btn = ft.IconButton(icon="play_circle_filled", icon_size=80, icon_color="white", disabled_color="white24", on_click=self.toggle_play_pause, disabled=True)
        self.prev_btn = ft.IconButton(icon="skip_previous", icon_size=40, icon_color="white", disabled_color="white24", disabled=True, on_click=self.onceki_sarki)
        self.next_btn = ft.IconButton(icon="skip_next", icon_size=40, icon_color="white", disabled_color="white24", disabled=True, on_click=self.sonraki_sarki)

        shuffle_col = self.current_theme_color if self.shuffle_mode else "white24"
        repeat_col = self.current_theme_color if self.repeat_mode else "white24"

        self.shuffle_btn = ft.IconButton(icon="shuffle", icon_size=24, icon_color=shuffle_col, on_click=self.toggle_shuffle)
        self.repeat_btn = ft.IconButton(icon="repeat", icon_size=24, icon_color=repeat_col, on_click=self.toggle_repeat)

        self.favori_butonu = ft.IconButton(icon="favorite_border", icon_size=26, icon_color="white", disabled_color="white24", on_click=self.favori_islem)
        self.indir_butonu = ft.IconButton(icon="download", icon_size=26, icon_color="white", disabled_color="white24", disabled=True, on_click=self.indirme_baslat)
        self.video_butonu = ft.IconButton(icon="ondemand_video", icon_size=26, icon_color="white", disabled_color="white24", disabled=True, on_click=self.videoyu_ac)

        self.sure_slider = ft.Slider(min=0, max=100, disabled=True, expand=True, height=20, on_change_start=self.slider_change_start, on_change_end=self.slider_change_end)
        self.ses_slider = ft.Slider(min=0, max=100, value=100, expand=True, height=20, on_change=self.ses_degisti)
        self.ses_ikonu = ft.IconButton(icon="volume_up", icon_size=20, icon_color="white54", on_click=self.sesi_kapat_ac)

        # --- VIEW TANIMLAMALARI ---
        self.view_kesfet = ft.Container(
            padding=0,
            expand=True,
            content=ft.Column([
                ft.Container(
                    padding=ft.padding.symmetric(horizontal=15, vertical=10),
                    content=ft.Row(
                        controls=[
                            ft.Row([
                                ft.Text("MyMusics", size=24, weight="bold", color=self.current_theme_color),
                                ft.Text(" BEDIRHANY", size=16, color="white", weight="bold", font_family="PorscheTarzi")
                            ], spacing=5, vertical_alignment=ft.CrossAxisAlignment.CENTER),

                            ft.PopupMenuButton(
                                icon="color_lens",
                                items=[
                                    ft.PopupMenuItem(text="Yeşil", on_click=lambda _: self.tema_degistir("green")),
                                    ft.PopupMenuItem(text="Mavi", on_click=lambda _: self.tema_degistir("blue")),
                                    ft.PopupMenuItem(text="Kırmızı", on_click=lambda _: self.tema_degistir("red")),
                                    ft.PopupMenuItem(text="Mor", on_click=lambda _: self.tema_degistir("purple")),
                                    ft.PopupMenuItem(text="Turuncu", on_click=lambda _: self.tema_degistir("orange")),
                                    ft.PopupMenuItem(text="Pembe", on_click=lambda _: self.tema_degistir("pink")),
                                ]
                            )
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN
                    )
                ),

                ft.Container(padding=ft.padding.only(left=15), content=ft.Text("Keşfet", size=28, weight="bold", color="white")),

                ft.Container(
                    padding=ft.padding.symmetric(horizontal=5),
                    content=ft.Row([
                        ft.ElevatedButton("Yerli", on_click=lambda _: self.kesfet_kategori_getir("Yerli"), bgcolor="green", color="white", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))),
                        ft.ElevatedButton("Yabancı", on_click=lambda _: self.kesfet_kategori_getir("Yabancı"), bgcolor="blue", color="white", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))),
                        ft.ElevatedButton("Mix", on_click=lambda _: self.kesfet_kategori_getir("Rastgele"), bgcolor="purple", color="white", style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10))),
                        ft.IconButton(icon="hourglass_bottom", on_click=self.zaman_yolculugu, icon_color="orange"),
                    ], scroll="auto"),
                    height=60
                ),
                self.kesfet_sonuclari
            ])
        )

        self.view_arama = ft.Container(
            padding=0,
            expand=True,
            content=ft.Column([
                ft.Container(padding=ft.padding.all(15), content=ft.Text("Arama", size=28, weight="bold", color="white")),
                ft.Container(padding=ft.padding.symmetric(horizontal=15), content=self.arama_kutusu),
                self.arama_sonuclari
            ])
        )

        self.view_kitaplik = ft.Container(
            padding=0,
            expand=True,
            content=ft.Column([
                ft.Container(padding=ft.padding.all(15), content=ft.Text("Kitaplık", size=28, weight="bold", color="white")),
                self.favori_sonuclari
            ])
        )

        # --- PLAYER DÜZENİ ---
        self.view_player = ft.Container(
            padding=0,
            alignment=ft.alignment.center,
            expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_center,
                end=ft.alignment.bottom_center,
                colors=["#1a1a1a", "#000000"]
            ),
            content=ft.Column([
                ft.Container(height=30),
                self.resim_konteyner,
                ft.Container(height=20),
                self.visualizer_row,
                ft.Container(height=10),

                ft.Column([
                    ft.Row(
                        controls=[
                            ft.Container(
                                content=self.suanki_sarki_adi,
                                width=280
                            ),
                            ft.IconButton(
                                icon="more_vert",
                                icon_color="white",
                                icon_size=28,
                                tooltip="Seçenekler",
                                on_click=lambda _: self.menuyu_ac(None, self.oynatma_listesi[self.suanki_index] if self.suanki_index != -1 else None)
                            )
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    self.durum_yazisi
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),

                ft.Container(height=30),

                ft.Row([self.gecen_sure_txt, self.sure_slider, self.toplam_sure_txt], alignment=ft.MainAxisAlignment.CENTER),

                ft.Row([self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn], alignment=ft.MainAxisAlignment.CENTER, spacing=15),

                ft.Container(height=20),

                ft.Row([
                    self.favori_butonu,
                    self.indir_butonu,
                    self.video_butonu,
                    ft.Container(width=20),
                    ft.Icon("volume_down", size=16, color="white54"),
                    self.ses_slider,
                    ft.Icon("volume_up", size=16, color="white54")
                ], alignment=ft.MainAxisAlignment.CENTER),

            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll="auto")
        )

        self.context_menu_items = ft.Column(tight=True)
        self.context_menu = ft.BottomSheet(
            ft.Container(
                self.context_menu_items,
                padding=20,
                border_radius=ft.border_radius.only(top_left=20, top_right=20),
                bgcolor="#222222",
            ),
            open=False
        )

    # ---------------------------
    # Yardımcı (audio uyumluluk) fonksiyonlar
    # ---------------------------
    def _audio_play(self):
        try:
            if not self.audio_player:
                return
            # bazı flet sürümlerinde play(), bazı sürümlerde resume() olabilir
            if hasattr(self.audio_player, "play"):
                self.audio_player.play()
            elif hasattr(self.audio_player, "resume"):
                self.audio_player.resume()
            else:
                # fallback: set autoplay and update
                try:
                    self.audio_player.autoplay = True
                    self.audio_player.update()
                except: pass
        except Exception:
            traceback.print_exc()

    def _audio_pause(self):
        try:
            if not self.audio_player:
                return
            if hasattr(self.audio_player, "pause"):
                self.audio_player.pause()
            elif hasattr(self.audio_player, "stop"):
                self.audio_player.stop()
            else:
                try:
                    self.audio_player.autoplay = False
                    self.audio_player.update()
                except: pass
        except Exception:
            traceback.print_exc()

    def _audio_seek(self, ms: int):
        try:
            if not self.audio_player:
                return
            if hasattr(self.audio_player, "seek"):
                # bazı sürümlerde seek saniye alıyor olabilir; deneyip uyum sağla
                try:
                    self.audio_player.seek(int(ms))
                except:
                    try:
                        self.audio_player.seek(int(ms / 1000))
                    except:
                        pass
            else:
                # yoksa ignore
                pass
        except Exception:
            traceback.print_exc()

    # ---------------------------

    def nav_degisti(self, e):
        index = e.control.selected_index
        try: self.page.controls.pop(0)
        except: pass

        if index == 0: self.page.controls.insert(0, self.view_kesfet)
        elif index == 1: self.page.controls.insert(0, self.view_arama)
        elif index == 2:
            self.favorileri_listele()
            self.page.controls.insert(0, self.view_kitaplik)
        elif index == 3: self.page.controls.insert(0, self.view_player)

        self.page.update()

    def zaman_yolculugu(self, e):
        yil = random.randint(1980, 2024)
        sorgu = f"Top hit songs of {yil} mix"
        self.page.snack_bar = ft.SnackBar(ft.Text(f"⏳ {yil} yılına gidiliyor..."), bgcolor="purple")
        self.page.snack_bar.open = True
        self.page.update()
        self.kesfet_kategori_getir("Zaman Yolcusu", custom_query=sorgu)

    def menu_islem(self, islem):
        if not self.secilen_menu_sarkisi: return
        self.context_menu.open = False
        self.context_menu.update()
        sarki = self.secilen_menu_sarkisi

        if islem == "indir":
            self.indir_butonu.data = sarki['id']
            old_title = self.suanki_sarki_adi.value
            if not self.caliniyor_mu: self.suanki_sarki_adi.value = sarki['title']
            self.indirme_baslat(None)
            if not self.caliniyor_mu: self.suanki_sarki_adi.value = old_title

        elif islem == "sil":
            self.sarkiyi_sil(sarki)

        elif islem == "kopyala":
            url = f"https://www.youtube.com/watch?v={sarki['id']}"
            self.page.set_clipboard(url)
            self.page.snack_bar = ft.SnackBar(ft.Text("Link kopyalandı!"))
            self.page.snack_bar.open = True

        elif islem == "favori_degistir":
            self.menu_favori_yap(sarki)

        self.page.update()

    def menuyu_ac(self, e, sarki):
        if not sarki: return
        self.secilen_menu_sarkisi = sarki

        temiz_isim = self.sanitize_filename(sarki['title'])
        indirildi = False
        if os.path.exists(self.indirilenler_klasoru):
            for dosya in os.listdir(self.indirilenler_klasoru):
                if temiz_isim in dosya:
                    indirildi = True
                    break

        favori_mi = any(s['id'] == sarki['id'] for s in self.favori_listesi)

        items = [
            ft.Text("Seçenekler", weight="bold", size=18, text_align="center"),
            ft.Divider(),
            ft.ListTile(leading=ft.Icon("play_arrow_rounded"), title=ft.Text("Hemen Oynat"), on_click=lambda _: self.menu_islem_oynat(sarki)),
        ]

        if favori_mi:
            items.append(ft.ListTile(leading=ft.Icon("favorite", color="red"), title=ft.Text("Favorilerden Çıkar", color="red"), on_click=lambda _: self.menu_islem("favori_degistir")))
        else:
            items.append(ft.ListTile(leading=ft.Icon("favorite_border"), title=ft.Text("Favorilere Ekle"), on_click=lambda _: self.menu_islem("favori_degistir")))

        if indirildi:
            items.append(ft.ListTile(leading=ft.Icon("delete", color="red"), title=ft.Text("Şarkıyı Sil", color="red"), on_click=lambda _: self.menu_islem("sil")))
        else:
            items.append(ft.ListTile(leading=ft.Icon("download"), title=ft.Text("İndir"), on_click=lambda _: self.menu_islem("indir")))

        items.append(ft.ListTile(leading=ft.Icon("copy"), title=ft.Text("Linki Kopyala"), on_click=lambda _: self.menu_islem("kopyala")))

        self.context_menu_items.controls = items
        self.context_menu.open = True
        self.context_menu.update()

    def menu_favori_yap(self, sarki):
        mevcut_idleri = [s['id'] for s in self.favori_listesi]
        if sarki['id'] in mevcut_idleri:
            self.favori_listesi = [s for s in self.favori_listesi if s['id'] != sarki['id']]
            msj = "Favorilerden çıkarıldı."
            if self.indir_butonu.data == sarki['id']:
                self.favori_butonu.icon = "favorite_border"
                self.favori_butonu.icon_color = "white"
        else:
            kayit_verisi = {'id': sarki['id'], 'title': sarki['title'], 'duration': sarki.get('duration', '00:00'), 'thumbnails': self.get_thumb_url(sarki)}
            self.favori_listesi.append(kayit_verisi)
            msj = "Favorilere eklendi ❤️"
            if self.indir_butonu.data == sarki['id']:
                self.favori_butonu.icon = "favorite"
                self.favori_butonu.icon_color = "red"

        try:
            with open(self.favoriler_dosyasi, "w", encoding="utf-8") as f: json.dump(self.favori_listesi, f)
        except: pass

        self.page.snack_bar = ft.SnackBar(ft.Text(msj))
        self.page.snack_bar.open = True
        if self.nav_bar.selected_index == 2: self.favorileri_listele()
        self.page.update()

    def sarkiyi_sil(self, sarki):
        try:
            temiz_isim = self.sanitize_filename(sarki['title'])
            silindi = False
            for dosya in os.listdir(self.indirilenler_klasoru):
                if temiz_isim in dosya:
                    os.remove(os.path.join(self.indirilenler_klasoru, dosya))
                    silindi = True
                    break

            if silindi:
                self.page.snack_bar = ft.SnackBar(ft.Text(f"{sarki['title']} silindi!"), bgcolor="red")
                self.indir_butonu.icon = "download"
                self.indir_butonu.icon_color = "white"
                self.indir_butonu.disabled = False
                if self.nav_bar.selected_index == 2: self.favorileri_listele()
            else:
                self.page.snack_bar = ft.SnackBar(ft.Text("Dosya zaten yok veya bulunamadı."))

            self.page.snack_bar.open = True
            self.page.update()
        except Exception as e:
            print("sarkiyi_sil hata:", e)

    def menu_islem_oynat(self, sarki):
        self.context_menu.open = False
        self.context_menu.update()
        self.oynatma_listesi = [sarki]
        self.oynat(0)

    def tema_degistir(self, renk):
        self.current_theme_color = renk
        self.settings["theme"] = renk
        self.save_settings()
        try:
            self.page.theme.color_scheme_seed = renk
        except: pass
        for bar in self.visualizer_bars: bar.bgcolor = renk
        self.shuffle_btn.icon_color = renk if self.shuffle_mode else "white24"
        self.repeat_btn.icon_color = renk if self.repeat_mode else "white24"
        if self.nav_bar.selected_index == 0:
            try: self.view_kesfet.content.controls[0].content.controls[0].controls[0].color = renk
            except: pass
        self.page.update()
        self.page.snack_bar = ft.SnackBar(ft.Text(f"Tema: {renk.capitalize()}"))
        self.page.snack_bar.open = True
        self.page.update()

    def visualizer_loop(self):
        while self.app_running:
            if self.view_player not in self.page.controls:
                time.sleep(0.5)
                continue

            if self.caliniyor_mu and self.visualizer_active:
                for bar in self.visualizer_bars: bar.height = random.randint(5, 40)
                if random.random() > 0.85:
                    neon = random.choice(self.neon_colors)
                    try:
                        self.resim_konteyner.shadow.color = neon
                        self.resim_konteyner.shadow.blur_radius = random.randint(20, 50)
                        self.resim_konteyner.update()
                    except: pass
                try:
                    self.visualizer_row.opacity = 1
                    self.visualizer_row.update()
                except: pass
                time.sleep(0.12)
            else:
                if self.visualizer_row.opacity != 0:
                    self.visualizer_row.opacity = 0
                    try:
                        self.visualizer_row.update()
                        self.resim_konteyner.shadow.color = "black"
                        self.resim_konteyner.shadow.blur_radius = 30
                        self.resim_konteyner.update()
                    except: pass
                time.sleep(0.5)

    def audio_state_changed(self, e):
        # e.data içeriklerine göre kontrol et
        try:
            if getattr(e, "data", None) == "completed":
                if self.repeat_mode:
                    # tekrar için seek 0 ve play
                    self._audio_seek(0)
                    self._audio_play()
                else:
                    self.sonraki_sarki(None)
        except Exception:
            traceback.print_exc()

    def slider_change_start(self, e): self.is_slider_changing = True

    def slider_change_end(self, e):
        try:
            if self.audio_player and getattr(self.audio_player, "src", None):
                # e.control.value ms cinsinden ayarlanmış olabilir
                val = int(e.control.value)
                self._audio_seek(val)
        except Exception:
            pass
        self.is_slider_changing = False

    def sure_guncelle(self, e):
        if self.is_slider_changing: return
        try:
            # e.data bazen ms bazen s olabilir; deneyip uygun şekilde ayarla
            pos = int(e.data)
            # Bazı durumlarda pos saniye olabiliyor -> eğer küçükse saniye mi diye kontrol et
            if pos < 1000:  # muhtemelen saniye
                pos_ms = pos * 1000
            else:
                pos_ms = pos
            self.sure_slider.value = pos_ms
            self.gecen_sure_txt.value = self.sure_formatla(pos_ms)
            self.page.update()
        except Exception:
            pass

    def oynat(self, index):
        if index < 0 or index >= len(self.oynatma_listesi): return

        self.suanki_index = index
        secilen_sarki = self.oynatma_listesi[index]
        video_id = secilen_sarki['id']
        title = secilen_sarki['title']
        thumb = self.get_thumb_url(secilen_sarki)

        self.nav_bar.selected_index = 3
        try: self.page.controls.pop(0)
        except: pass
        self.page.controls.insert(0, self.view_player)

        self.durum_yazisi.value = "Bağlanıyor..."
        self.play_btn.icon = "hourglass_empty"
        self.play_btn.disabled = True
        self.loading_indicator.visible = True

        self.page.update()

        def background_load():
            try:
                temiz_ad = self.sanitize_filename(title)
                bulunan_dosya = None
                if os.path.exists(self.indirilenler_klasoru):
                    for f in os.listdir(self.indirilenler_klasoru):
                        if temiz_ad in f:
                            bulunan_dosya = os.path.join(self.indirilenler_klasoru, f)
                            break
                src = ""
                duration_sec = 0
                if bulunan_dosya:
                    src = os.path.abspath(bulunan_dosya)
                    duration_sec = self.parse_duration(secilen_sarki.get('duration', '00:00'))
                else:
                    tam_link = f"https://www.youtube.com/watch?v={video_id}"
                    src, _, duration_sec = self.get_audio_url(tam_link)

                if not src:
                    raise Exception("Kaynak yok")

                def update_ui_safe():
                    try:
                        # audio_player'u güncelle ve çal
                        if self.audio_player:
                            self.audio_player.src = src
                            # autoplay boş bir ayar yerine oynatma çağır
                            self.audio_player.update()
                            # Kısa bir gecikme istemeden doğrudan play çağır
                            self._audio_play()

                        self.caliniyor_mu = True
                        self.play_btn.icon = "pause_circle_filled"
                        self.play_btn.disabled = False
                        self.prev_btn.disabled = False
                        self.next_btn.disabled = False
                        self.suanki_sarki_adi.value = title
                        self.suanki_resim.src = thumb

                        self.loading_indicator.visible = False
                        self.resim_konteyner.content.scale = 1.0

                        toplam_ms = duration_sec * 1000 if isinstance(duration_sec, (int, float)) else self.parse_duration(secilen_sarki.get('duration', '00:00')) * 1000
                        if toplam_ms > 0:
                            self.sure_slider.max = toplam_ms
                            self.sure_slider.disabled = False
                        else:
                            self.sure_slider.disabled = True
                        self.toplam_sure_txt.value = self.sure_formatla(toplam_ms)
                        self.durum_yazisi.value = "Çalınıyor"

                        mevcut_idleri = [s['id'] for s in self.favori_listesi]
                        if video_id in mevcut_idleri:
                            self.favori_butonu.icon = "favorite"
                            self.favori_butonu.icon_color = "red"
                        else:
                            self.favori_butonu.icon = "favorite_border"
                            self.favori_butonu.icon_color = "white"

                        self.favori_butonu.data = secilen_sarki
                        self.video_butonu.disabled = False
                        self.video_butonu.data = video_id

                        indirildi_mi = False
                        if os.path.exists(self.indirilenler_klasoru):
                            for f in os.listdir(self.indirilenler_klasoru):
                                if temiz_ad in f:
                                    indirildi_mi = True
                                    break

                        if indirildi_mi:
                            self.indir_butonu.icon = "check_circle"
                            self.indir_butonu.icon_color = "green"
                            self.indir_butonu.disabled = True
                        else:
                            self.indir_butonu.icon = "download"
                            self.indir_butonu.icon_color = "white"
                            self.indir_butonu.disabled = False
                            self.indir_butonu.data = video_id

                        self.page.update()
                    except Exception:
                        traceback.print_exc()

                try: self.page.run_task(update_ui_safe)
                except: update_ui_safe()

            except Exception as err:
                print(f"Oynatma hatası: {err}")
                traceback.print_exc()
                def error_ui():
                    self.durum_yazisi.value = "Hata oluştu"
                    self.play_btn.disabled = False
                    self.loading_indicator.visible = False
                    self.play_btn.icon = "play_circle_filled"
                    self.page.update()
                try: self.page.run_task(error_ui)
                except: error_ui()

        threading.Thread(target=background_load, daemon=True).start()

    def toggle_play_pause(self, e):
        if not self.audio_player or not getattr(self.audio_player, "src", None):
            return
        if self.caliniyor_mu:
            # pause
            self._audio_pause()
            self.play_btn.icon = "play_circle_filled"
            self.durum_yazisi.value = "Duraklatıldı"
            self.caliniyor_mu = False
            try: self.resim_konteyner.content.scale = 0.95
            except: pass
            self.visualizer_active = False
        else:
            # resume/play
            self._audio_play()
            self.play_btn.icon = "pause_circle_filled"
            self.durum_yazisi.value = "Çalınıyor"
            self.caliniyor_mu = True
            try: self.resim_konteyner.content.scale = 1.0
            except: pass
            self.visualizer_active = True

        try:
            self.audio_player.update()
        except: pass
        self.page.update()

    def sonraki_sarki(self, e):
        if not self.oynatma_listesi: return
        yeni_index = self.suanki_index
        if self.shuffle_mode: yeni_index = random.randint(0, len(self.oynatma_listesi) - 1)
        else:
            if self.suanki_index < len(self.oynatma_listesi) - 1: yeni_index = self.suanki_index + 1
            else: yeni_index = 0
        self.oynat(yeni_index)

    def onceki_sarki(self, e):
        if not self.oynatma_listesi: return
        if self.suanki_index > 0: self.oynat(self.suanki_index - 1)
        else: self.oynat(len(self.oynatma_listesi) - 1)

    def sanitize_filename(self, filename): return re.sub(r'[\\/*?:"<>|]', "", filename).strip()

    def indirme_baslat(self, e):
        if not getattr(self.indir_butonu, "data", None): return
        video_id = self.indir_butonu.data
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        self.indir_butonu.icon = "downloading"
        self.indir_butonu.icon_color = "yellow"
        self.indir_butonu.disabled = True
        self.loading_indicator.visible = True
        self.resim_konteyner.update()
        self.page.update()

        def indir_thread():
            try:
                sarki_adi = self.sanitize_filename(self.suanki_sarki_adi.value)
                ydl_opts = {'format': 'bestaudio/best', 'outtmpl': f'{self.indirilenler_klasoru}/{sarki_adi}.%(ext)s', 'quiet': True, 'nocheckcertificate': True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl: ydl.download([video_url])

                def success():
                    self.indir_butonu.icon = "check_circle"
                    self.indir_butonu.icon_color = "green"
                    self.loading_indicator.visible = False
                    self.resim_konteyner.update()
                    self.page.snack_bar = ft.SnackBar(ft.Text(f"{sarki_adi} indirildi!"), bgcolor="green")
                    self.page.snack_bar.open = True
                    self.page.update()
                    time.sleep(2)
                    self.indir_butonu.disabled = True
                    self.page.update()
                try: self.page.run_task(success)
                except: success()
            except Exception as err:
                print(f"Hata: {err}")
                traceback.print_exc()
                def fail():
                    self.indir_butonu.icon = "error_outline"
                    self.indir_butonu.icon_color = "red"
                    self.loading_indicator.visible = False
                    self.resim_konteyner.update()
                    self.page.update()
                    time.sleep(2)
                    self.indir_butonu.icon = "download"
                    self.indir_butonu.disabled = False
                    self.page.update()
                try: self.page.run_task(fail)
                except: fail()

        threading.Thread(target=indir_thread, daemon=True).start()

    def favorileri_listele(self, filtre=""):
        self.favori_sonuclari.controls.clear()
        indirilenler = []
        try: indirilenler = os.listdir(self.indirilenler_klasoru)
        except: pass
        if not self.favori_listesi:
            self.favori_sonuclari.controls.append(ft.Text("Henüz favori şarkınız yok.", text_align="center"))
        for song in self.favori_listesi:
            if filtre and filtre.lower() not in song['title'].lower(): continue
            temiz_isim = self.sanitize_filename(song['title'])
            indirildi_mi = any(temiz_isim in dosya for dosya in indirilenler)
            self.favori_sonuclari.controls.append(self.liste_karti_olustur(song, self.favori_listesi, indirildi_mi=indirildi_mi))
        self.page.update()

    def liste_karti_olustur(self, veri, liste_referansi, indirildi_mi=False):
        thumb = self.get_thumb_url(veri)
        content_container = ft.Container(
            content=ft.Row([
                ft.Image(src=thumb, width=60, height=60, border_radius=10, fit=ft.ImageFit.COVER),
                ft.Column([
                    ft.Text(veri['title'], max_lines=1, width=200, weight="bold", size=15, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Row([ft.Icon("check_circle", size=12, color="green"), ft.Text("İndirildi", size=10, color="green")]) if indirildi_mi else ft.Text(veri.get('duration', ''), size=12, color="grey")
                ], spacing=2, alignment=ft.MainAxisAlignment.CENTER),
                ft.Container(expand=True),
                ft.IconButton(icon="more_vert", icon_size=20, icon_color="grey", on_click=lambda e: self.menuyu_ac(e, veri))
            ]),
            padding=10,
            bgcolor="#15ffffff",
            border_radius=15,
        )
        return ft.GestureDetector(
            mouse_cursor=ft.MouseCursor.CLICK,
            on_tap=lambda e: self.liste_sarki_secildi(veri, liste_referansi),
            content=content_container
        )

    def liste_sarki_secildi(self, sarki_verisi, kaynak_liste):
        if not sarki_verisi and kaynak_liste: sarki_verisi = kaynak_liste[0]
        hedef_id = sarki_verisi['id']

        if kaynak_liste != self.oynatma_listesi:
            self.oynatma_listesi = list(kaynak_liste)

        for i, s in enumerate(self.oynatma_listesi):
            if s['id'] == hedef_id:
                self.oynat(i)
                break

    def arama_yap(self, e):
        query = self.arama_kutusu.value
        if not query: return
        self.nav_bar.selected_index = 1
        try: self.page.controls.pop(0)
        except: pass
        self.page.controls.insert(0, self.view_arama)

        self.arama_sonuclari.controls.clear()
        self.arama_sonuclari.controls.append(ft.ProgressBar(width=300, color="green"))
        self.page.update()
        def arama_thread():
            try:
                results = YoutubeSearch(query, max_results=20).to_dict()
                def ui_update():
                    self.arama_sonuclari.controls.clear()
                    if not results: self.arama_sonuclari.controls.append(ft.Text("Sonuç bulunamadı."))
                    for res in results: self.arama_sonuclari.controls.append(self.liste_karti_olustur(res, results))
                    self.page.update()
                try: self.page.run_task(ui_update)
                except: ui_update()
            except Exception as ex:
                print("arama_hata:", ex)
        threading.Thread(target=arama_thread, daemon=True).start()

    def kesfet_kategori_getir(self, kategori, custom_query=None):
        anahtar_kelimeler = {
            "Yerli": "Türkçe Pop 2025 Hit Şarkılar",
            "Yabancı": "Global Top 50 Songs 2025",
            "Nostalji": "90lar Türkçe Pop",
            "Rastgele": f"Mix Music {random.randint(2018, 2025)} hit"
        }
        terim = custom_query if custom_query else anahtar_kelimeler.get(kategori, "Müzik")
        self.kesfet_sonuclari.controls.clear()
        self.kesfet_sonuclari.controls.append(ft.ProgressBar(color="blue"))
        self.page.update()
        def thread_func():
            try:
                res = YoutubeSearch(terim, max_results=20).to_dict()
                random.shuffle(res)
                def ui():
                    self.kesfet_sonuclari.controls.clear()
                    baslik = f"⏳ {kategori}" if custom_query else f"💿 {kategori}"
                    self.kesfet_sonuclari.controls.append(ft.Text(baslik, size=18, weight="bold"))
                    for r in res: self.kesfet_sonuclari.controls.append(self.liste_karti_olustur(r, res))
                    self.page.update()
                try: self.page.run_task(ui)
                except: ui()
            except Exception as ex:
                print("kesfet_hata:", ex)
        threading.Thread(target=thread_func, daemon=True).start()

    def get_audio_url(self, video_url):
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'force_ipv4': True,
            'socket_timeout': 10
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                return info.get('url'), info.get('title', 'Bilinmeyen'), info.get('duration', 0)
        except Exception as e:
            print("get_audio_url hata:", e)
            return None, None, 0

    def get_thumb_url(self, data):
        if 'thumbnails' in data:
            t = data['thumbnails']
            if isinstance(t, list) and t: return t[-1]['url'] if isinstance(t[-1], dict) else t[0]
            return t
        elif 'thumb' in data: return data['thumb']
        return "https://upload.wikimedia.org/wikipedia/commons/1/14/No_Image_Available.jpg"

    def sure_formatla(self, ms):
        if ms is None: return "00:00"
        s = int(ms / 1000)
        return f"{s // 60:02}:{s % 60:02}"

    def parse_duration(self, duration_str):
        try:
            parts = str(duration_str).split(':')
            if len(parts) == 2: return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3: return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            return int(duration_str) if str(duration_str).isdigit() else 0
        except: return 0

    def favori_islem(self, e):
        if not getattr(self.favori_butonu, "data", None): return
        data = self.favori_butonu.data
        mevcut_idleri = [s['id'] for s in self.favori_listesi]
        if data['id'] in mevcut_idleri:
            self.favori_listesi = [s for s in self.favori_listesi if s['id'] != data['id']]
            self.favori_butonu.icon = "favorite_border"
            self.favori_butonu.icon_color = "white"
        else:
            kayit_verisi = {'id': data['id'], 'title': data['title'], 'duration': data.get('duration', '00:00'), 'thumbnails': self.get_thumb_url(data)}
            self.favori_listesi.append(kayit_verisi)
            self.favori_butonu.icon = "favorite"
            self.favori_butonu.icon_color = "red"
        try:
            with open(self.favoriler_dosyasi, "w", encoding="utf-8") as f: json.dump(self.favori_listesi, f)
        except: pass
        self.page.update()

    def videoyu_ac(self, e):
        if getattr(self.video_butonu, "data", None): self.page.launch_url(f"https://www.youtube.com/watch?v={self.video_butonu.data}")

    def ses_degisti(self, e):
        vol = self.ses_slider.value / 100
        try:
            if self.audio_player:
                self.audio_player.volume = vol
                self.audio_player.update()
        except: pass
        if vol == 0: self.ses_ikonu.icon = "volume_off"
        elif vol < 0.5: self.ses_ikonu.icon = "volume_down"
        else: self.ses_ikonu.icon = "volume_up"
        self.ses_ikonu.update()
        self.settings["volume"] = vol
        self.save_settings()

    def sesi_kapat_ac(self, e):
        try:
            if self.audio_player and getattr(self.audio_player, "volume", 0) > 0:
                self.settings["last_vol"] = self.audio_player.volume
                self.audio_player.volume = 0
                self.ses_slider.value = 0
                self.ses_ikonu.icon = "volume_off"
            else:
                vol = self.settings.get("last_vol", 1.0)
                if self.audio_player:
                    self.audio_player.volume = vol
                self.ses_slider.value = vol * 100
                self.ses_ikonu.icon = "volume_up"
            if self.audio_player: self.audio_player.update()
            self.ses_slider.update()
        except Exception:
            traceback.print_exc()

    def toggle_shuffle(self, e):
        self.shuffle_mode = not self.shuffle_mode
        self.shuffle_btn.icon_color = self.current_theme_color if self.shuffle_mode else "white24"
        self.settings["shuffle"] = self.shuffle_mode
        self.save_settings()
        self.page.update()

    def toggle_repeat(self, e):
        self.repeat_mode = not self.repeat_mode
        self.repeat_btn.icon_color = self.current_theme_color if self.repeat_mode else "white24"
        self.settings["repeat"] = self.repeat_mode
        self.save_settings()
        self.page.update()


def main(page: ft.Page):
    page.fonts = {
        "PorscheTarzi": "https://github.com/google/fonts/raw/main/ofl/brunoacesc/BrunoAceSC-Regular.ttf"
    }
    # Android'te overlay kontrolleri, eksik izinler veya farklı davranışlar olabileceğinden
    # page.window_maximized = True  # gerekirse
    MusicApp(page)

if __name__ == "__main__":
    ft.app(target=main)
