/*
 * abcl_gui_runtime.c
 * ABCL/c+ → C 翻訳器が呼び出す GUI ビルトイン群 (SDL2)
 *
 * 翻訳器が出す .c は value_t / enqueue / abcl_shutdown / global_shutdown を
 * extern 公開しているので、ここで参照できる。
 *
 *   extern される本ファイルの API:
 *     value_t gui_open(int n, value_t* a);            // (w, h, title)
 *     value_t gui_set_line(int n, value_t* a);        // (idx, x1, y1, x2, y2 [,r,g,b])
 *     value_t gui_add_button(int n, value_t* a);      // (label, x, y, w, h, target, method)
 *     value_t gui_register_ticker(int n, value_t* a); // (target)
 *     value_t gui_run(int n, value_t* a);             // SDL ループ (ブロック)
 *     value_t b_sin(int n, value_t* a);
 *     value_t b_cos(int n, value_t* a);
 */

#include <SDL.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

/* --- 翻訳器側と一致させる value_t / vtag_t (生成 .c と同じ定義) --- */
typedef enum { V_NIL, V_INT, V_FLOAT, V_STR, V_OBJ } vtag_t;
typedef struct {
  vtag_t tag;
  long   i;
  double f;
  const char* s;
  int    obj_id;
} value_t;

/* --- 生成 .c から提供される API --- */
extern void enqueue(int sender, int receiver, const char* method,
                    int n_args, value_t* args);
extern void abcl_shutdown(void);
extern volatile int global_shutdown;

/* --- value_t 取り出しヘルパ --- */
static double val_d(value_t v) {
  switch (v.tag) {
  case V_INT:   return (double)v.i;
  case V_FLOAT: return v.f;
  default:      return 0.0;
  }
}
static long val_l(value_t v) {
  switch (v.tag) {
  case V_INT:   return v.i;
  case V_FLOAT: return (long)v.f;
  default:      return 0;
  }
}
static const char* val_s(value_t v) { return v.tag == V_STR ? (v.s ? v.s : "") : ""; }
static int val_o(value_t v) { return v.tag == V_OBJ ? v.obj_id : (int)val_l(v); }

static value_t v_nil(void) { value_t v={0}; v.tag=V_NIL; return v; }
static value_t v_int(long n){ value_t v={0}; v.tag=V_INT; v.i=n; return v; }

/* ===== 数学ビルトイン ===== */
value_t b_sin(int n, value_t* a) {
  value_t r={0}; r.tag=V_FLOAT;
  r.f = (n>=1) ? sin(val_d(a[0])) : 0.0;
  return r;
}
value_t b_cos(int n, value_t* a) {
  value_t r={0}; r.tag=V_FLOAT;
  r.f = (n>=1) ? cos(val_d(a[0])) : 0.0;
  return r;
}

/* ===== GUI 状態 ===== */
#define MAX_LINES   16
#define MAX_BUTTONS 8
#define MAX_TICKERS 16
#define MAX_PHILS   8
#define MAX_FORKS   8
#define MAX_SLOTS   32
#define MAX_ACTORS  8
#define MAX_SLIDERS 4
#define MAX_SIM_USERS    32
#define MAX_SIM_OBS      8

typedef struct {
  int    valid;
  double x1, y1, x2, y2;
  int    r, g, b;
} gline_t;

typedef struct {
  SDL_Rect    rect;
  char        label[32];
  int         target_obj;
  char        method[32];
  int         color_r, color_g, color_b;
  int         pressed;
} gbutton_t;

typedef struct {
  int    valid;
  double cx, cy, radius;
  int    state;   /* 0=thinking, 1=hungry, 2=eating */
} gphil_t;

typedef struct {
  int    valid;
  /* x1,y1: 反時計回り側 (= phil_(i-1)%N の側 = 「左隣」)
     x2,y2: 時計回り側     (= phil_i        の側 = 「右隣」) */
  double x1, y1, x2, y2;
  int    held;    /* 0=free, 1=held */
  int    holder;
  int    left_phil;   /* x1 端側にいる哲学者の idx */
  int    right_phil;  /* x2 端側にいる哲学者の idx */
} gfork_t;

static gline_t   g_lines[MAX_LINES];
static gbutton_t g_buttons[MAX_BUTTONS];
static int       g_n_buttons = 0;
static int       g_tickers[MAX_TICKERS];
static int       g_n_tickers = 0;
static gphil_t   g_phils[MAX_PHILS];
static gfork_t   g_forks[MAX_FORKS];

/* 有限バッファ問題用 */
typedef struct {
  int      valid;
  int      filled;
  int      producer_id;
  SDL_Rect rect;
} gslot_t;

typedef struct {
  int    valid;
  int    type;     /* 0=producer, 1=consumer */
  int    state;    /* 0=idle, 1=working, 2=waiting/req */
  double cx, cy, radius;
} gact_t;

static int     g_buf_capacity = 0;
static int     g_buf_head     = 0;   /* take ポインタ */
static int     g_buf_tail     = 0;   /* put ポインタ  */
static gslot_t g_slots[MAX_SLOTS];
static gact_t  g_producers[MAX_ACTORS];
static gact_t  g_consumers[MAX_ACTORS];
static int     g_n_producers = 0;
static int     g_n_consumers = 0;

/* スライダー */
typedef struct {
  int      valid;
  SDL_Rect rect;
  int      track_id;
  int      min_val, max_val, current_val;
  Uint8    fill_r, fill_g, fill_b;
  char     label[8];
} gslider_t;

static gslider_t g_sliders[MAX_SLIDERS];
static int       g_n_sliders   = 0;
static int       g_drag_slider = -1;

/* ========= 帰宅支援シミュレータ (論文 ICAART2016 by Taga et al.) =========
   2 つの world を並べて同時実行。
   world A: システム未使用 (情報共有なし)
   world B: システム使用   (MANET 内で発見済み impassable 情報を共有)
*/

typedef struct {
  double  x, y;
  int     state;       /* 0=walking, 1=safe, 2=dead */
  unsigned long known; /* 発見済み obstacle のビットマスク */
  double  stamina;
  double  init_x, init_y;
} sim_user_t;

typedef struct {
  SDL_Rect bounds;          /* この world の描画矩形       */
  SDL_Rect obstacles[MAX_SIM_OBS];
  int      n_obstacles;
  SDL_Rect safe_zone;
  sim_user_t users[MAX_SIM_USERS];
  int      n_users;
  int      use_system;      /* 0=without, 1=with */
  int      n_safe;
  int      n_dead;
  int      n_walking;
} sim_world_t;

static sim_world_t g_world_a;   /* without system */
static sim_world_t g_world_b;   /* with    system */
static int         g_sim_initialized = 0;
static double      g_sim_view_range = 55.0;
static double      g_sim_comm_range = 90.0;
static double      g_sim_step       = 1.4;
static double      g_sim_stamina0   = 1500.0;

static SDL_Window*   g_win = NULL;
static SDL_Renderer* g_ren = NULL;
static int           g_win_w = 480, g_win_h = 480;

static pthread_mutex_t g_gui_mu = PTHREAD_MUTEX_INITIALIZER;

/* ===== GUI ビルトイン ===== */
value_t gui_open(int n, value_t* a) {
  if (n >= 1) g_win_w = (int)val_d(a[0]);
  if (n >= 2) g_win_h = (int)val_d(a[1]);
  /* 実際の SDL_CreateWindow は gui_run() 内 (メインスレッドで初期化) */
  return v_nil();
}

value_t gui_set_line(int n, value_t* a) {
  if (n < 5) return v_nil();
  int idx = (int)val_d(a[0]);
  if (idx < 0 || idx >= MAX_LINES) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  g_lines[idx].valid = 1;
  g_lines[idx].x1 = val_d(a[1]);
  g_lines[idx].y1 = val_d(a[2]);
  g_lines[idx].x2 = val_d(a[3]);
  g_lines[idx].y2 = val_d(a[4]);
  if (n >= 8) {
    g_lines[idx].r = (int)val_d(a[5]);
    g_lines[idx].g = (int)val_d(a[6]);
    g_lines[idx].b = (int)val_d(a[7]);
  } else {
    g_lines[idx].r = 200; g_lines[idx].g = 220; g_lines[idx].b = 255;
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_add_button(int n, value_t* a) {
  if (n < 7) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_n_buttons >= MAX_BUTTONS) { pthread_mutex_unlock(&g_gui_mu); return v_nil(); }
  gbutton_t* b = &g_buttons[g_n_buttons++];
  const char* lab = val_s(a[0]);
  strncpy(b->label, lab, sizeof b->label - 1);
  b->label[sizeof b->label - 1] = '\0';
  b->rect.x = (int)val_d(a[1]);
  b->rect.y = (int)val_d(a[2]);
  b->rect.w = (int)val_d(a[3]);
  b->rect.h = (int)val_d(a[4]);
  b->target_obj = val_o(a[5]);
  const char* m = val_s(a[6]);
  strncpy(b->method, m, sizeof b->method - 1);
  b->method[sizeof b->method - 1] = '\0';
  if      (strcmp(b->label, "Start") == 0) { b->color_r= 60; b->color_g=170; b->color_b= 90; }
  else if (strcmp(b->label, "Stop")  == 0) { b->color_r=200; b->color_g= 80; b->color_b= 80; }
  else                                     { b->color_r=120; b->color_g=120; b->color_b=140; }
  b->pressed = 0;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_register_ticker(int n, value_t* a) {
  if (n < 1) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_n_tickers < MAX_TICKERS) {
    g_tickers[g_n_tickers++] = val_o(a[0]);
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* ===== 哲学者問題用 ===== */

/* gui_dining_init(N): N 人の哲学者・N 本のフォークを正多角形配置 */
value_t gui_dining_init(int n, value_t* a) {
  int N = (n >= 1) ? (int)val_d(a[0]) : 5;
  if (N > MAX_PHILS) N = MAX_PHILS;
  pthread_mutex_lock(&g_gui_mu);
  double cx = g_win_w * 0.5;
  double cy = g_win_h * 0.42;
  double Rphil = 150.0;
  double Rfork = 110.0;
  for (int i = 0; i < N; i++) {
    double a0 = -M_PI/2.0 + 2.0*M_PI*(double)i/(double)N;
    g_phils[i].valid  = 1;
    g_phils[i].cx     = cx + cos(a0) * Rphil;
    g_phils[i].cy     = cy + sin(a0) * Rphil;
    g_phils[i].radius = 28;
    g_phils[i].state  = 0;
  }
  for (int i = 0; i < N; i++) {
    /* fork i は philosopher (i-1+N)%N と philosopher i の間
       (アクター側: phil_i.left = fork_i, phil_(i-1).right = fork_i) */
    double a0 = -M_PI/2.0 + 2.0*M_PI*((double)i - 0.5)/(double)N;
    double fx = cx + cos(a0) * Rfork;
    double fy = cy + sin(a0) * Rfork;
    /* tangent (tx,ty) は a0 が増える方向 = 時計回り = phil_i に向かう */
    double tx = -sin(a0), ty = cos(a0);
    double len = 24.0;
    g_forks[i].valid      = 1;
    g_forks[i].x1         = fx - tx * len;   /* 反時計回り側 = phil_(i-1) */
    g_forks[i].y1         = fy - ty * len;
    g_forks[i].x2         = fx + tx * len;   /* 時計回り側   = phil_i      */
    g_forks[i].y2         = fy + ty * len;
    g_forks[i].held       = 0;
    g_forks[i].holder     = -1;
    g_forks[i].left_phil  = (i - 1 + N) % N;
    g_forks[i].right_phil = i;
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_set_phil(int n, value_t* a) {
  if (n < 2) return v_nil();
  int idx = (int)val_d(a[0]);
  int st  = (int)val_d(a[1]);
  if (idx < 0 || idx >= MAX_PHILS) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_phils[idx].valid) g_phils[idx].state = st;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_set_fork_held(int n, value_t* a) {
  if (n < 2) return v_nil();
  int idx    = (int)val_d(a[0]);
  int holder = (int)val_d(a[1]);
  if (idx < 0 || idx >= MAX_FORKS) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_forks[idx].valid) { g_forks[idx].held = 1; g_forks[idx].holder = holder; }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_set_fork_free(int n, value_t* a) {
  if (n < 1) return v_nil();
  int idx = (int)val_d(a[0]);
  if (idx < 0 || idx >= MAX_FORKS) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_forks[idx].valid) { g_forks[idx].held = 0; g_forks[idx].holder = -1; }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* ===== 有限バッファ用 ===== */

/* 配色: 各 producer に固有の色 */
static void producer_color(int pid, Uint8* r, Uint8* g, Uint8* b) {
  static const Uint8 palette[6][3] = {
    {220,  90,  90},   /* red    */
    { 90, 200, 130},   /* green  */
    { 90, 140, 230},   /* blue   */
    {220, 180,  90},   /* amber  */
    {180,  90, 220},   /* purple */
    { 90, 200, 220},   /* cyan   */
  };
  int i = ((pid % 6) + 6) % 6;
  *r = palette[i][0]; *g = palette[i][1]; *b = palette[i][2];
}

value_t gui_buf_setup(int n, value_t* a) {
  if (n < 3) return v_nil();
  int cap = (int)val_d(a[0]);
  int npr = (int)val_d(a[1]);
  int nco = (int)val_d(a[2]);
  if (cap > MAX_SLOTS)  cap = MAX_SLOTS;
  if (npr > MAX_ACTORS) npr = MAX_ACTORS;
  if (nco > MAX_ACTORS) nco = MAX_ACTORS;
  pthread_mutex_lock(&g_gui_mu);
  g_buf_capacity = cap;
  g_buf_head = 0; g_buf_tail = 0;
  g_n_producers = npr; g_n_consumers = nco;

  /* 4 つ目の引数が来ていれば「下端で予約する高さ」として扱う (スライダー＋ボタン用) */
  int reserve_bottom = (n >= 4) ? (int)val_d(a[3]) : 130;
  int top_y_layout   = 90;
  int bot_y_layout   = g_win_h - reserve_bottom;
  if (bot_y_layout < top_y_layout + 100) bot_y_layout = top_y_layout + 100;

  /* バッファスロット: アクター領域の縦中央に横一列。
     producer/consumer の円のため左右に 100px 確保し、残り幅を slot 数で割る */
  int actor_margin = 100;
  int avail_w = g_win_w - 2 * actor_margin;
  if (avail_w < cap * 14) avail_w = cap * 14;
  int slot_w = avail_w / cap;
  if (slot_w > 50) slot_w = 50;
  if (slot_w < 14) slot_w = 14;
  int slot_h = slot_w + 8;
  if (slot_h > 50) slot_h = 50;
  int total_w = cap * slot_w;
  int start_x = (g_win_w - total_w) / 2;
  int slot_y  = (top_y_layout + bot_y_layout) / 2 - slot_h / 2;
  for (int i = 0; i < cap; i++) {
    g_slots[i].valid       = 1;
    g_slots[i].filled      = 0;
    g_slots[i].producer_id = -1;
    g_slots[i].rect.x = start_x + i * slot_w;
    g_slots[i].rect.y = slot_y;
    g_slots[i].rect.w = slot_w - 4;
    g_slots[i].rect.h = slot_h - 4;
  }
  /* producer: 左端に縦並び */
  int margin = 60;
  int top_y  = top_y_layout + 20;
  int bot_y  = bot_y_layout - 20;
  for (int i = 0; i < npr; i++) {
    double t = (npr > 1) ? (double)i / (double)(npr - 1) : 0.5;
    g_producers[i].valid  = 1;
    g_producers[i].type   = 0;
    g_producers[i].state  = 0;
    g_producers[i].cx     = (double)margin;
    g_producers[i].cy     = top_y + t * (bot_y - top_y);
    g_producers[i].radius = 26;
  }
  /* consumer: 右端に縦並び */
  for (int i = 0; i < nco; i++) {
    double t = (nco > 1) ? (double)i / (double)(nco - 1) : 0.5;
    g_consumers[i].valid  = 1;
    g_consumers[i].type   = 1;
    g_consumers[i].state  = 0;
    g_consumers[i].cx     = (double)(g_win_w - margin);
    g_consumers[i].cy     = top_y + t * (bot_y - top_y);
    g_consumers[i].radius = 26;
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_buf_put(int n, value_t* a) {
  if (n < 1 || g_buf_capacity <= 0) return v_nil();
  int pid = (int)val_d(a[0]);
  pthread_mutex_lock(&g_gui_mu);
  int slot = g_buf_tail % g_buf_capacity;
  g_slots[slot].filled      = 1;
  g_slots[slot].producer_id = pid;
  g_buf_tail = (g_buf_tail + 1) % g_buf_capacity;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_buf_take(int n, value_t* a) {
  (void)n; (void)a;
  if (g_buf_capacity <= 0) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  int slot = g_buf_head % g_buf_capacity;
  g_slots[slot].filled      = 0;
  g_slots[slot].producer_id = -1;
  g_buf_head = (g_buf_head + 1) % g_buf_capacity;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* ========= 帰宅支援シミュレータ ========= */

/* 同じ初期配置を 2 つの world にセット */
static void sim_init_world(sim_world_t* w, int use_system, SDL_Rect bounds, int n_users) {
  w->bounds = bounds;
  w->use_system = use_system;
  w->n_users = (n_users > MAX_SIM_USERS) ? MAX_SIM_USERS : n_users;

  /* obstacle: 4 個固定 (相対座標で配置) */
  int W = bounds.w, H = bounds.h;
  w->n_obstacles = 4;
  w->obstacles[0] = (SDL_Rect){ bounds.x + (int)(W*0.30), bounds.y + (int)(H*0.10), (int)(W*0.10), (int)(H*0.30) };
  w->obstacles[1] = (SDL_Rect){ bounds.x + (int)(W*0.20), bounds.y + (int)(H*0.55), (int)(W*0.18), (int)(H*0.20) };
  w->obstacles[2] = (SDL_Rect){ bounds.x + (int)(W*0.55), bounds.y + (int)(H*0.30), (int)(W*0.12), (int)(H*0.30) };
  w->obstacles[3] = (SDL_Rect){ bounds.x + (int)(W*0.55), bounds.y + (int)(H*0.75), (int)(W*0.18), (int)(H*0.13) };

  /* safe zone: 右端に縦長 */
  w->safe_zone = (SDL_Rect){ bounds.x + W - 40, bounds.y + (int)(H*0.20),
                             32, (int)(H*0.60) };

  /* user: 左端に縦並び */
  for (int i = 0; i < w->n_users; i++) {
    double t = (w->n_users > 1) ? (double)i / (double)(w->n_users - 1) : 0.5;
    w->users[i].init_x = bounds.x + 20 + ((i * 7) % 14);
    w->users[i].init_y = bounds.y + 30 + t * (H - 60);
    w->users[i].x      = w->users[i].init_x;
    w->users[i].y      = w->users[i].init_y;
    w->users[i].state  = 0;
    w->users[i].known  = 0;
    w->users[i].stamina = g_sim_stamina0;
  }
  w->n_safe = 0; w->n_dead = 0; w->n_walking = w->n_users;
}

static void sim_reset_users(sim_world_t* w) {
  for (int i = 0; i < w->n_users; i++) {
    w->users[i].x = w->users[i].init_x;
    w->users[i].y = w->users[i].init_y;
    w->users[i].state = 0;
    w->users[i].known = 0;
    w->users[i].stamina = g_sim_stamina0;
  }
  w->n_safe = 0; w->n_dead = 0; w->n_walking = w->n_users;
}

value_t gui_disaster_setup(int n, value_t* a) {
  pthread_mutex_lock(&g_gui_mu);
  int n_users = (n >= 1) ? (int)val_d(a[0]) : 16;
  /* 上に余白 (タイトル) を確保し、下にボタン用の余白を残す */
  int title_h    = 30;
  int bottom_res = 90;
  int field_h    = g_win_h - title_h - bottom_res;
  int half_w     = (g_win_w - 30) / 2;   /* 中央 10px の溝 */
  SDL_Rect ba = { 10,                    title_h, half_w, field_h };
  SDL_Rect bb = { 10 + half_w + 10,      title_h, half_w, field_h };
  sim_init_world(&g_world_a, 0, ba, n_users);
  sim_init_world(&g_world_b, 1, bb, n_users);
  g_sim_initialized = 1;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_disaster_reset(int n, value_t* a) {
  (void)n; (void)a;
  pthread_mutex_lock(&g_gui_mu);
  if (g_sim_initialized) {
    sim_reset_users(&g_world_a);
    sim_reset_users(&g_world_b);
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* world 内 1 ステップ進める */
static void sim_step_world(sim_world_t* w) {
  /* 1. 視界内 obstacle 発見 */
  for (int i = 0; i < w->n_users; i++) {
    if (w->users[i].state != 0) continue;
    for (int o = 0; o < w->n_obstacles; o++) {
      double cx = w->obstacles[o].x + w->obstacles[o].w * 0.5;
      double cy = w->obstacles[o].y + w->obstacles[o].h * 0.5;
      double dx = cx - w->users[i].x;
      double dy = cy - w->users[i].y;
      double r  = sqrt(dx*dx + dy*dy);
      double obs_r = (w->obstacles[o].w + w->obstacles[o].h) * 0.5;
      if (r < g_sim_view_range + obs_r * 0.5) {
        w->users[i].known |= (1UL << o);
      }
    }
  }

  /* 2. with-system: comm range 内でビットマスク OR  */
  if (w->use_system) {
    for (int i = 0; i < w->n_users; i++) {
      if (w->users[i].state != 0) continue;
      for (int j = i + 1; j < w->n_users; j++) {
        if (w->users[j].state != 0) continue;
        double dx = w->users[i].x - w->users[j].x;
        double dy = w->users[i].y - w->users[j].y;
        if (dx*dx + dy*dy < g_sim_comm_range * g_sim_comm_range) {
          unsigned long m = w->users[i].known | w->users[j].known;
          w->users[i].known = m;
          w->users[j].known = m;
        }
      }
    }
  }

  /* 3. 移動 */
  int safe = 0, dead = 0, walk = 0;
  for (int i = 0; i < w->n_users; i++) {
    if (w->users[i].state == 1) { safe++; continue; }
    if (w->users[i].state == 2) { dead++; continue; }

    double gx = w->safe_zone.x + w->safe_zone.w * 0.5;
    double gy = w->safe_zone.y + w->safe_zone.h * 0.5;
    double dx = gx - w->users[i].x;
    double dy = gy - w->users[i].y;
    double dist = sqrt(dx*dx + dy*dy);
    if (dist < 0.1) { w->users[i].state = 1; safe++; continue; }
    dx /= dist; dy /= dist;

    /* 既知 obstacle からの斥力 */
    for (int o = 0; o < w->n_obstacles; o++) {
      if (!(w->users[i].known & (1UL << o))) continue;
      double cx = w->obstacles[o].x + w->obstacles[o].w * 0.5;
      double cy = w->obstacles[o].y + w->obstacles[o].h * 0.5;
      double rx = w->users[i].x - cx;
      double ry = w->users[i].y - cy;
      double r2 = rx*rx + ry*ry;
      double rad = (w->obstacles[o].w + w->obstacles[o].h) * 0.5 + 30.0;
      if (r2 < rad * rad) {
        double r = sqrt(r2);
        if (r > 0.5) {
          double f = (rad - r) / rad * 2.6;
          dx += (rx / r) * f;
          dy += (ry / r) * f;
        }
      }
    }

    /* 正規化して 1 ステップ進める */
    double mag = sqrt(dx*dx + dy*dy);
    if (mag > 1e-3) { dx /= mag; dy /= mag; }
    w->users[i].x += dx * g_sim_step;
    w->users[i].y += dy * g_sim_step;
    w->users[i].stamina -= 1.0;

    /* 衝突判定: obstacle に踏み込んだら死亡 */
    for (int o = 0; o < w->n_obstacles; o++) {
      SDL_Rect* r = &w->obstacles[o];
      if (w->users[i].x >= r->x && w->users[i].x < r->x + r->w &&
          w->users[i].y >= r->y && w->users[i].y < r->y + r->h) {
        w->users[i].state = 2;
        break;
      }
    }
    /* スタミナ切れも死亡 */
    if (w->users[i].state == 0 && w->users[i].stamina <= 0) {
      w->users[i].state = 2;
    }
    /* safe zone に入ったら救助 */
    if (w->users[i].state == 0) {
      SDL_Rect* r = &w->safe_zone;
      if (w->users[i].x >= r->x && w->users[i].x < r->x + r->w &&
          w->users[i].y >= r->y && w->users[i].y < r->y + r->h) {
        w->users[i].state = 1;
      }
    }

    if      (w->users[i].state == 1) safe++;
    else if (w->users[i].state == 2) dead++;
    else                              walk++;
  }
  w->n_safe = safe; w->n_dead = dead; w->n_walking = walk;
}

value_t gui_disaster_step(int n, value_t* a) {
  (void)n; (void)a;
  if (!g_sim_initialized) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  sim_step_world(&g_world_a);
  sim_step_world(&g_world_b);
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* スライダー (track_id, x, y, w, h, min, max, init [, r, g, b, label]) */
value_t gui_add_slider(int n, value_t* a) {
  if (n < 8) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if (g_n_sliders >= MAX_SLIDERS) { pthread_mutex_unlock(&g_gui_mu); return v_nil(); }
  gslider_t* s = &g_sliders[g_n_sliders++];
  s->valid       = 1;
  s->track_id    = (int)val_d(a[0]);
  s->rect.x      = (int)val_d(a[1]);
  s->rect.y      = (int)val_d(a[2]);
  s->rect.w      = (int)val_d(a[3]);
  s->rect.h      = (int)val_d(a[4]);
  s->min_val     = (int)val_d(a[5]);
  s->max_val     = (int)val_d(a[6]);
  s->current_val = (int)val_d(a[7]);
  if (s->current_val < s->min_val) s->current_val = s->min_val;
  if (s->current_val > s->max_val) s->current_val = s->max_val;
  if (n >= 11) {
    s->fill_r = (Uint8)val_d(a[8]);
    s->fill_g = (Uint8)val_d(a[9]);
    s->fill_b = (Uint8)val_d(a[10]);
  } else {
    s->fill_r = 200; s->fill_g = 200; s->fill_b = 220;
  }
  if (n >= 12) {
    const char* lab = val_s(a[11]);
    strncpy(s->label, lab, sizeof s->label - 1);
    s->label[sizeof s->label - 1] = '\0';
  } else {
    s->label[0] = '\0';
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

value_t gui_slider_value(int n, value_t* a) {
  if (n < 1) return v_int(0);
  int track_id = (int)val_d(a[0]);
  int val = 0;
  pthread_mutex_lock(&g_gui_mu);
  for (int i = 0; i < g_n_sliders; i++) {
    if (g_sliders[i].valid && g_sliders[i].track_id == track_id) {
      val = g_sliders[i].current_val;
      break;
    }
  }
  pthread_mutex_unlock(&g_gui_mu);
  return v_int(val);
}

static void slider_update_from_x(int idx, int mx) {
  pthread_mutex_lock(&g_gui_mu);
  if (idx >= 0 && idx < g_n_sliders && g_sliders[idx].valid) {
    gslider_t* s = &g_sliders[idx];
    int rx = mx - s->rect.x;
    if (rx < 0) rx = 0;
    if (rx > s->rect.w) rx = s->rect.w;
    int range = s->max_val - s->min_val;
    s->current_val = s->min_val + (rx * range + s->rect.w / 2) / (s->rect.w > 0 ? s->rect.w : 1);
  }
  pthread_mutex_unlock(&g_gui_mu);
}

value_t gui_set_actor(int n, value_t* a) {
  if (n < 3) return v_nil();
  int idx   = (int)val_d(a[0]);
  int type  = (int)val_d(a[1]);
  int state = (int)val_d(a[2]);
  if (idx < 0 || idx >= MAX_ACTORS) return v_nil();
  pthread_mutex_lock(&g_gui_mu);
  if      (type == 0 && g_producers[idx].valid) g_producers[idx].state = state;
  else if (type == 1 && g_consumers[idx].valid) g_consumers[idx].state = state;
  pthread_mutex_unlock(&g_gui_mu);
  return v_nil();
}

/* 8x10 ピクセル簡易フォント (I/N/O/U/T のみ)。x,y は左上 */
static void draw_letter(SDL_Renderer* r, char c, int x, int y) {
  switch (c) {
    case 'I':
      SDL_RenderDrawLine(r, x+1, y,   x+6, y);
      SDL_RenderDrawLine(r, x+1, y+1, x+6, y+1);
      SDL_RenderDrawLine(r, x+1, y+9, x+6, y+9);
      SDL_RenderDrawLine(r, x+1, y+8, x+6, y+8);
      SDL_RenderDrawLine(r, x+3, y+1, x+3, y+8);
      SDL_RenderDrawLine(r, x+4, y+1, x+4, y+8);
      break;
    case 'N':
      SDL_RenderDrawLine(r, x,   y, x,   y+9);
      SDL_RenderDrawLine(r, x+1, y, x+1, y+9);
      SDL_RenderDrawLine(r, x+6, y, x+6, y+9);
      SDL_RenderDrawLine(r, x+7, y, x+7, y+9);
      SDL_RenderDrawLine(r, x,   y, x+7, y+9);
      SDL_RenderDrawLine(r, x+1, y, x+7, y+8);
      break;
    case 'O':
      SDL_RenderDrawLine(r, x+2, y,   x+5, y);
      SDL_RenderDrawLine(r, x+2, y+1, x+5, y+1);
      SDL_RenderDrawLine(r, x+2, y+9, x+5, y+9);
      SDL_RenderDrawLine(r, x+2, y+8, x+5, y+8);
      SDL_RenderDrawLine(r, x,   y+2, x,   y+7);
      SDL_RenderDrawLine(r, x+1, y+2, x+1, y+7);
      SDL_RenderDrawLine(r, x+6, y+2, x+6, y+7);
      SDL_RenderDrawLine(r, x+7, y+2, x+7, y+7);
      break;
    case 'U':
      SDL_RenderDrawLine(r, x,   y,   x,   y+7);
      SDL_RenderDrawLine(r, x+1, y,   x+1, y+7);
      SDL_RenderDrawLine(r, x+6, y,   x+6, y+7);
      SDL_RenderDrawLine(r, x+7, y,   x+7, y+7);
      SDL_RenderDrawLine(r, x+2, y+9, x+5, y+9);
      SDL_RenderDrawLine(r, x+2, y+8, x+5, y+8);
      break;
    case 'T':
      SDL_RenderDrawLine(r, x,   y,   x+7, y);
      SDL_RenderDrawLine(r, x,   y+1, x+7, y+1);
      SDL_RenderDrawLine(r, x+3, y+2, x+3, y+9);
      SDL_RenderDrawLine(r, x+4, y+2, x+4, y+9);
      break;
    default: break;
  }
}

static void draw_text(SDL_Renderer* r, const char* s, int x, int y) {
  while (*s) {
    draw_letter(r, *s, x, y);
    x += 10;
    s++;
  }
}

/* 矢印 (tail → head)。 head 側に三角形の鏃。3px 厚の軸 */
static void draw_arrow(SDL_Renderer* r, int xt, int yt, int xh, int yh) {
  /* 軸を 3 ライン分太らせる */
  SDL_RenderDrawLine(r, xt,   yt,   xh,   yh);
  SDL_RenderDrawLine(r, xt+1, yt,   xh+1, yh);
  SDL_RenderDrawLine(r, xt,   yt+1, xh,   yh+1);

  double dx = (double)(xh - xt);
  double dy = (double)(yh - yt);
  double L  = sqrt(dx*dx + dy*dy);
  if (L < 1.0) return;
  dx /= L; dy /= L;
  /* 軸方向に対して垂直単位ベクトル */
  double px = -dy, py = dx;
  double head_back = 11.0;
  double head_side = 6.0;
  int bx = xh - (int)(dx * head_back);
  int by = yh - (int)(dy * head_back);
  int p1x = bx + (int)(px * head_side);
  int p1y = by + (int)(py * head_side);
  int p2x = bx - (int)(px * head_side);
  int p2y = by - (int)(py * head_side);
  /* 三角形の鏃 (3 ライン) */
  SDL_RenderDrawLine(r, xh,  yh,  p1x, p1y);
  SDL_RenderDrawLine(r, xh,  yh,  p2x, p2y);
  SDL_RenderDrawLine(r, p1x, p1y, p2x, p2y);
}

/* 円塗りつぶし／輪郭 */
static void fill_circle(SDL_Renderer* r, int cx, int cy, int rad) {
  for (int dy = -rad; dy <= rad; dy++) {
    int dx = (int)sqrt((double)(rad*rad - dy*dy));
    SDL_RenderDrawLine(r, cx - dx, cy + dy, cx + dx, cy + dy);
  }
}
static void draw_circle_outline(SDL_Renderer* r, int cx, int cy, int rad) {
  int x = rad, y = 0, err = 0;
  while (x >= y) {
    SDL_RenderDrawPoint(r, cx + x, cy + y);
    SDL_RenderDrawPoint(r, cx + y, cy + x);
    SDL_RenderDrawPoint(r, cx - y, cy + x);
    SDL_RenderDrawPoint(r, cx - x, cy + y);
    SDL_RenderDrawPoint(r, cx - x, cy - y);
    SDL_RenderDrawPoint(r, cx - y, cy - x);
    SDL_RenderDrawPoint(r, cx + y, cy - x);
    SDL_RenderDrawPoint(r, cx + x, cy - y);
    y += 1; err += 1 + 2*y;
    if (2*(err - x) + 1 > 0) { x -= 1; err += 1 - 2*x; }
  }
}

/* ボタン中央にアイコンを描画 */
static void draw_button_icon(SDL_Renderer* r, gbutton_t* b) {
  SDL_SetRenderDrawColor(r, 255, 255, 255, 255);
  int cx = b->rect.x + b->rect.w / 2;
  int cy = b->rect.y + b->rect.h / 2;
  if (strcmp(b->label, "Start") == 0) {
    /* play triangle ▶ */
    int size = 9;
    for (int dy = -size; dy <= size; dy++) {
      int half = size - abs(dy);
      for (int dx = -size; dx <= half; dx++) {
        if (dx <= half) SDL_RenderDrawPoint(r, cx + dx - 2, cy + dy);
      }
    }
  } else if (strcmp(b->label, "Stop") == 0) {
    /* square ■ */
    SDL_Rect sq = { cx - 7, cy - 7, 14, 14 };
    SDL_RenderFillRect(r, &sq);
  }
}

value_t gui_run(int n, value_t* a) {
  (void)n; (void)a;
  if (SDL_Init(SDL_INIT_VIDEO) != 0) {
    fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
    abcl_shutdown();
    return v_nil();
  }
  g_win = SDL_CreateWindow("ABCL/c+ Rotate4Lines",
                           SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
                           g_win_w, g_win_h, SDL_WINDOW_SHOWN);
  if (!g_win) {
    fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
    abcl_shutdown();
    return v_nil();
  }
  g_ren = SDL_CreateRenderer(g_win, -1,
                             SDL_RENDERER_ACCELERATED | SDL_RENDERER_PRESENTVSYNC);
  if (!g_ren) {
    fprintf(stderr, "SDL_CreateRenderer: %s\n", SDL_GetError());
    abcl_shutdown();
    return v_nil();
  }
  /* macOS で確実に最前面に出す */
  SDL_ShowWindow(g_win);
  SDL_RaiseWindow(g_win);
  SDL_SetWindowInputFocus(g_win);

  fprintf(stderr, "[gui] window opened %dx%d, buttons=%d, tickers=%d\n",
          g_win_w, g_win_h, g_n_buttons, g_n_tickers);

  Uint32 last_tick = SDL_GetTicks();
  SDL_Event ev;
  int running = 1;
  int frames = 0;
  while (running && !global_shutdown) {
    while (SDL_PollEvent(&ev)) {
      if (ev.type == SDL_QUIT) running = 0;
      else if (ev.type == SDL_MOUSEBUTTONDOWN && ev.button.button == SDL_BUTTON_LEFT) {
        int mx = ev.button.x, my = ev.button.y;
        /* スライダー優先 */
        int slider_hit = -1;
        pthread_mutex_lock(&g_gui_mu);
        for (int i = 0; i < g_n_sliders; i++) {
          gslider_t* s = &g_sliders[i];
          if (!s->valid) continue;
          if (mx >= s->rect.x - 6 && mx < s->rect.x + s->rect.w + 6 &&
              my >= s->rect.y - 6 && my < s->rect.y + s->rect.h + 6) {
            slider_hit = i;
            break;
          }
        }
        pthread_mutex_unlock(&g_gui_mu);
        if (slider_hit >= 0) {
          g_drag_slider = slider_hit;
          slider_update_from_x(slider_hit, mx);
        } else {
          /* ボタン */
          pthread_mutex_lock(&g_gui_mu);
          for (int i = 0; i < g_n_buttons; i++) {
            gbutton_t* b = &g_buttons[i];
            if (mx >= b->rect.x && mx < b->rect.x + b->rect.w &&
                my >= b->rect.y && my < b->rect.y + b->rect.h) {
              b->pressed = 6;
              int target = b->target_obj;
              char meth[32]; strcpy(meth, b->method);
              pthread_mutex_unlock(&g_gui_mu);
              enqueue(-1, target, strdup(meth), 0, NULL);
              pthread_mutex_lock(&g_gui_mu);
            }
          }
          pthread_mutex_unlock(&g_gui_mu);
        }
      }
      else if (ev.type == SDL_MOUSEMOTION) {
        if (g_drag_slider >= 0) slider_update_from_x(g_drag_slider, ev.motion.x);
      }
      else if (ev.type == SDL_MOUSEBUTTONUP && ev.button.button == SDL_BUTTON_LEFT) {
        g_drag_slider = -1;
      }
    }

    /* 16ms 周期で全 ticker に tick() を送る */
    Uint32 now = SDL_GetTicks();
    if (now - last_tick >= 16) {
      last_tick = now;
      pthread_mutex_lock(&g_gui_mu);
      int nt = g_n_tickers;
      int targets[MAX_TICKERS];
      for (int i = 0; i < nt; i++) targets[i] = g_tickers[i];
      pthread_mutex_unlock(&g_gui_mu);
      for (int i = 0; i < nt; i++) enqueue(-1, targets[i], "tick", 0, NULL);
    }

    /* 描画 */
    SDL_SetRenderDrawColor(g_ren, 18, 20, 30, 255);
    SDL_RenderClear(g_ren);

    pthread_mutex_lock(&g_gui_mu);
    for (int i = 0; i < MAX_LINES; i++) {
      if (g_lines[i].valid) {
        SDL_SetRenderDrawColor(g_ren,
          (Uint8)g_lines[i].r, (Uint8)g_lines[i].g, (Uint8)g_lines[i].b, 255);
        SDL_RenderDrawLine(g_ren,
          (int)g_lines[i].x1, (int)g_lines[i].y1,
          (int)g_lines[i].x2, (int)g_lines[i].y2);
      }
    }
    /* フォーク */
    for (int i = 0; i < MAX_FORKS; i++) {
      if (!g_forks[i].valid) continue;
      int x1 = (int)g_forks[i].x1, y1 = (int)g_forks[i].y1;
      int x2 = (int)g_forks[i].x2, y2 = (int)g_forks[i].y2;
      if (!g_forks[i].held) {
        /* 空: 平坦な線分 (3px 厚) */
        SDL_SetRenderDrawColor(g_ren, 200, 200, 200, 255);
        SDL_RenderDrawLine(g_ren, x1,   y1,   x2,   y2);
        SDL_RenderDrawLine(g_ren, x1+1, y1,   x2+1, y2);
        SDL_RenderDrawLine(g_ren, x1,   y1+1, x2,   y2+1);
      } else {
        /* 占有: 保持者の方向に矢印 */
        SDL_SetRenderDrawColor(g_ren, 240, 200, 80, 255);
        if (g_forks[i].holder == g_forks[i].right_phil) {
          /* 右隣 (= phil_i, x2 端側) が保持 → 矢印は x1 → x2 */
          draw_arrow(g_ren, x1, y1, x2, y2);
        } else if (g_forks[i].holder == g_forks[i].left_phil) {
          /* 左隣 (= phil_(i-1), x1 端側) が保持 → 矢印は x2 → x1 */
          draw_arrow(g_ren, x2, y2, x1, y1);
        } else {
          SDL_RenderDrawLine(g_ren, x1, y1, x2, y2);
        }
      }
    }
    /* 有限バッファ問題: スロット */
    if (g_buf_capacity > 0) {
      for (int i = 0; i < g_buf_capacity; i++) {
        if (!g_slots[i].valid) continue;
        SDL_Rect r = g_slots[i].rect;
        SDL_SetRenderDrawColor(g_ren, 35, 38, 50, 255);
        SDL_RenderFillRect(g_ren, &r);
        if (g_slots[i].filled) {
          Uint8 cr, cg, cb;
          producer_color(g_slots[i].producer_id, &cr, &cg, &cb);
          SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
          SDL_Rect inner = { r.x + 5, r.y + 5, r.w - 10, r.h - 10 };
          SDL_RenderFillRect(g_ren, &inner);
        }
        SDL_SetRenderDrawColor(g_ren, 200, 200, 220, 255);
        SDL_RenderDrawRect(g_ren, &r);
      }
    }
    /* producer */
    for (int i = 0; i < g_n_producers; i++) {
      if (!g_producers[i].valid) continue;
      Uint8 cr, cg, cb; producer_color(i, &cr, &cg, &cb);
      switch (g_producers[i].state) {
        case 0: cr = (Uint8)(cr/3); cg = (Uint8)(cg/3); cb = (Uint8)(cb/3); break;  /* idle: 暗 */
        case 1: break;                                                              /* working: 自色 */
        case 2: cr = 240; cg = 200; cb = 80;                                  break; /* waiting: 黄 */
      }
      SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
      fill_circle(g_ren, (int)g_producers[i].cx, (int)g_producers[i].cy, (int)g_producers[i].radius);
      SDL_SetRenderDrawColor(g_ren, 240, 240, 240, 255);
      draw_circle_outline(g_ren, (int)g_producers[i].cx, (int)g_producers[i].cy, (int)g_producers[i].radius);
    }
    /* consumer */
    for (int i = 0; i < g_n_consumers; i++) {
      if (!g_consumers[i].valid) continue;
      Uint8 cr = 80, cg = 200, cb = 130;
      switch (g_consumers[i].state) {
        case 0: cr = 60;  cg = 80;  cb = 80;  break; /* idle    */
        case 1: cr = 90;  cg = 220; cb = 140; break; /* eating  */
        case 2: cr = 240; cg = 200; cb = 80;  break; /* waiting */
      }
      SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
      fill_circle(g_ren, (int)g_consumers[i].cx, (int)g_consumers[i].cy, (int)g_consumers[i].radius);
      SDL_SetRenderDrawColor(g_ren, 240, 240, 240, 255);
      draw_circle_outline(g_ren, (int)g_consumers[i].cx, (int)g_consumers[i].cy, (int)g_consumers[i].radius);
    }

    /* 哲学者 */
    for (int i = 0; i < MAX_PHILS; i++) {
      if (!g_phils[i].valid) continue;
      Uint8 cr=80, cg=120, cb=240;
      switch (g_phils[i].state) {
        case 0: cr= 80; cg=130; cb=230; break; /* thinking 青  */
        case 1: cr=240; cg=200; cb= 80; break; /* hungry   黄 */
        case 2: cr= 80; cg=200; cb=120; break; /* eating   緑 */
      }
      SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
      fill_circle(g_ren, (int)g_phils[i].cx, (int)g_phils[i].cy, (int)g_phils[i].radius);
      SDL_SetRenderDrawColor(g_ren, 240, 240, 240, 255);
      draw_circle_outline(g_ren, (int)g_phils[i].cx, (int)g_phils[i].cy, (int)g_phils[i].radius);
    }
    /* 帰宅支援シミュレータの 2 ワールド */
    if (g_sim_initialized) {
      sim_world_t* worlds[2] = { &g_world_a, &g_world_b };
      for (int wi = 0; wi < 2; wi++) {
        sim_world_t* w = worlds[wi];

        /* タイトルストリップ: A=赤(without), B=緑(with) */
        SDL_Rect title = { w->bounds.x, 5, w->bounds.w, 22 };
        if (w->use_system) SDL_SetRenderDrawColor(g_ren, 50, 130, 80, 255);
        else               SDL_SetRenderDrawColor(g_ren, 150, 60, 60, 255);
        SDL_RenderFillRect(g_ren, &title);
        SDL_SetRenderDrawColor(g_ren, 240, 240, 240, 255);
        SDL_RenderDrawRect(g_ren, &title);

        /* タイトルテキスト */
        if (w->use_system) draw_text(g_ren, "TIH",  title.x + 8, title.y + 6); /* "WITH" の擬似 */
        else                draw_text(g_ren, "OUT",   title.x + 8, title.y + 6);

        /* フィールド枠 */
        SDL_SetRenderDrawColor(g_ren, 25, 28, 38, 255);
        SDL_RenderFillRect(g_ren, &w->bounds);
        SDL_SetRenderDrawColor(g_ren, 90, 95, 115, 255);
        SDL_RenderDrawRect(g_ren, &w->bounds);

        /* safe zone */
        SDL_SetRenderDrawColor(g_ren, 60, 160, 90, 255);
        SDL_RenderFillRect(g_ren, &w->safe_zone);
        SDL_SetRenderDrawColor(g_ren, 180, 240, 200, 255);
        SDL_RenderDrawRect(g_ren, &w->safe_zone);

        /* obstacles (impassable points) */
        for (int o = 0; o < w->n_obstacles; o++) {
          SDL_SetRenderDrawColor(g_ren, 170, 70, 70, 255);
          SDL_RenderFillRect(g_ren, &w->obstacles[o]);
          SDL_SetRenderDrawColor(g_ren, 240, 200, 200, 255);
          SDL_RenderDrawRect(g_ren, &w->obstacles[o]);
        }

        /* MANET 通信リンク (with-system のみ淡く描く) */
        if (w->use_system) {
          SDL_SetRenderDrawColor(g_ren, 70, 110, 140, 255);
          for (int i = 0; i < w->n_users; i++) {
            if (w->users[i].state != 0) continue;
            for (int j = i + 1; j < w->n_users; j++) {
              if (w->users[j].state != 0) continue;
              double dx = w->users[i].x - w->users[j].x;
              double dy = w->users[i].y - w->users[j].y;
              if (dx*dx + dy*dy < g_sim_comm_range * g_sim_comm_range) {
                SDL_RenderDrawLine(g_ren,
                  (int)w->users[i].x, (int)w->users[i].y,
                  (int)w->users[j].x, (int)w->users[j].y);
              }
            }
          }
        }

        /* user dots */
        for (int i = 0; i < w->n_users; i++) {
          int ix = (int)w->users[i].x;
          int iy = (int)w->users[i].y;
          int rad = 4;
          Uint8 cr, cg, cb;
          switch (w->users[i].state) {
            case 1: cr =  90; cg = 230; cb = 130; break; /* safe  緑 */
            case 2: cr =  90; cg =  90; cb = 100; break; /* dead  灰 */
            default:cr = 240; cg = 220; cb =  80; break; /* walk  黄 */
          }
          SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
          fill_circle(g_ren, ix, iy, rad);
        }

        /* 統計バー (フィールド下) */
        int total = w->n_users > 0 ? w->n_users : 1;
        int bar_y = w->bounds.y + w->bounds.h + 8;
        int bar_w = w->bounds.w;
        int bar_h = 14;
        int safe_w = bar_w * w->n_safe / total;
        int dead_w = bar_w * w->n_dead / total;
        int walk_w = bar_w - safe_w - dead_w;
        SDL_Rect rs = { w->bounds.x,                     bar_y, safe_w, bar_h };
        SDL_Rect rw = { w->bounds.x + safe_w,            bar_y, walk_w, bar_h };
        SDL_Rect rd = { w->bounds.x + safe_w + walk_w,   bar_y, dead_w, bar_h };
        SDL_SetRenderDrawColor(g_ren,  90, 220, 130, 255); SDL_RenderFillRect(g_ren, &rs);
        SDL_SetRenderDrawColor(g_ren, 200, 200,  90, 255); SDL_RenderFillRect(g_ren, &rw);
        SDL_SetRenderDrawColor(g_ren, 200,  90,  90, 255); SDL_RenderFillRect(g_ren, &rd);
        SDL_Rect outline = { w->bounds.x, bar_y, bar_w, bar_h };
        SDL_SetRenderDrawColor(g_ren, 180, 180, 200, 255);
        SDL_RenderDrawRect(g_ren, &outline);
      }
    }

    /* スライダー */
    for (int i = 0; i < g_n_sliders; i++) {
      gslider_t* s = &g_sliders[i];
      if (!s->valid) continue;
      /* track */
      SDL_SetRenderDrawColor(g_ren, 50, 55, 70, 255);
      SDL_RenderFillRect(g_ren, &s->rect);
      /* fill (現在値まで) */
      double frac = 0.0;
      int range = s->max_val - s->min_val;
      if (range > 0) frac = (double)(s->current_val - s->min_val) / (double)range;
      if (frac < 0) frac = 0; if (frac > 1) frac = 1;
      SDL_Rect filled = { s->rect.x, s->rect.y, (int)(s->rect.w * frac), s->rect.h };
      SDL_SetRenderDrawColor(g_ren, s->fill_r, s->fill_g, s->fill_b, 255);
      SDL_RenderFillRect(g_ren, &filled);
      /* thumb */
      int tx = s->rect.x + (int)(s->rect.w * frac);
      SDL_Rect thumb = { tx - 4, s->rect.y - 5, 8, s->rect.h + 10 };
      SDL_SetRenderDrawColor(g_ren, 245, 245, 245, 255);
      SDL_RenderFillRect(g_ren, &thumb);
      /* outline */
      SDL_SetRenderDrawColor(g_ren, 200, 200, 220, 255);
      SDL_RenderDrawRect(g_ren, &s->rect);
      /* ラベル (左側に IN / OUT 等) */
      if (s->label[0]) {
        SDL_SetRenderDrawColor(g_ren, 230, 230, 240, 255);
        draw_text(g_ren, s->label, s->rect.x - 36, s->rect.y - 1);
      }
    }

    for (int i = 0; i < g_n_buttons; i++) {
      gbutton_t* b = &g_buttons[i];
      Uint8 cr = (Uint8)b->color_r, cg = (Uint8)b->color_g, cb = (Uint8)b->color_b;
      if (b->pressed > 0) { cr=(Uint8)(cr+40<255?cr+40:255); cg=(Uint8)(cg+40<255?cg+40:255); cb=(Uint8)(cb+40<255?cb+40:255); b->pressed--; }
      SDL_SetRenderDrawColor(g_ren, cr, cg, cb, 255);
      SDL_RenderFillRect(g_ren, &b->rect);
      SDL_SetRenderDrawColor(g_ren, 240, 240, 240, 255);
      SDL_RenderDrawRect(g_ren, &b->rect);
      draw_button_icon(g_ren, b);
    }
    pthread_mutex_unlock(&g_gui_mu);

    SDL_RenderPresent(g_ren);
    frames++;
  }
  fprintf(stderr, "[gui] loop exit: frames=%d\n", frames);

  /* ウィンドウ閉鎖時はアクター群もまとめて停止させる */
  abcl_shutdown();

  if (g_ren) SDL_DestroyRenderer(g_ren);
  if (g_win) SDL_DestroyWindow(g_win);
  SDL_Quit();
  return v_nil();
}
