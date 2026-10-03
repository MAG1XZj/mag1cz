// overlay_demo.as
// School project: "How game overlays work"
//
// Draws ESP-style visuals (boxes, names, health bars, distance, skeletons,
// snaplines) over a SIMULATED 3D scene. Every actor, the camera and the
// world-to-screen projection are computed inside this script, so it doesn't
// attach to or read memory from any game. It shows the overlay pipeline:
//   world position -> camera space -> perspective projection -> 2D drawing.

// ---------------------------------------------------------------------------
// Menu handles
// ---------------------------------------------------------------------------
checkbox cb_enabled;
checkbox cb_boxes;
checkbox cb_names;
checkbox cb_health;
checkbox cb_distance;
checkbox cb_skeleton;
checkbox cb_snaplines;
checkbox cb_grid;
color_picker col_team_a;
color_picker col_team_b;
color_picker col_skeleton;
combobox cmb_box_style;
slider sl_max_dist;
slider sl_cam_speed;
slider sl_fov;

// ---------------------------------------------------------------------------
// Simulated scene
// ---------------------------------------------------------------------------
class sim_actor {
    string name;
    int team;
    float health;
    float orbit_center_x;
    float orbit_center_y;
    float orbit_radius;
    float orbit_angle;
    float orbit_speed;
    float walk_phase;

    // derived each frame
    vec3 pos;
    float yaw;
}

array<sim_actor@> g_actors;
float g_time = 0.0f;
float g_cam_angle = 0.0f;

// camera basis (rebuilt every frame)
vec3 g_cam_pos;
vec3 g_cam_fwd;
vec3 g_cam_right;
vec3 g_cam_up;
float g_focal = 1.0f;
float g_screen_w = 1920.0f;
float g_screen_h = 1080.0f;

sim_actor@ make_actor(string name, int team, float cx, float cy, float radius, float speed, float start) {
    sim_actor a;
    a.name = name;
    a.team = team;
    a.health = 100.0f;
    a.orbit_center_x = cx;
    a.orbit_center_y = cy;
    a.orbit_radius = radius;
    a.orbit_speed = speed;
    a.orbit_angle = start;
    a.walk_phase = start * 3.0f;
    return a;
}

void build_scene() {
    g_actors.resize(0);
    g_actors.insertLast(make_actor("Alpha",   0, -400.0f,  200.0f, 300.0f,  0.6f, 0.0f));
    g_actors.insertLast(make_actor("Bravo",   0, -300.0f, -500.0f, 250.0f, -0.5f, 1.5f));
    g_actors.insertLast(make_actor("Charlie", 0,    0.0f,    0.0f, 700.0f,  0.3f, 3.0f));
    g_actors.insertLast(make_actor("Delta",   1,  500.0f,  300.0f, 350.0f, -0.7f, 0.7f));
    g_actors.insertLast(make_actor("Echo",    1,  400.0f, -400.0f, 200.0f,  0.9f, 2.2f));
    g_actors.insertLast(make_actor("Foxtrot", 1,  900.0f,    0.0f, 400.0f,  0.4f, 4.1f));
}

void update_scene(float dt) {
    g_time += dt;
    for (uint i = 0; i < g_actors.length(); i++) {
        sim_actor@ a = g_actors[i];
        a.orbit_angle += a.orbit_speed * dt;
        a.walk_phase += dt * 6.0f;
        float x = a.orbit_center_x + cos(a.orbit_angle) * a.orbit_radius;
        float y = a.orbit_center_y + sin(a.orbit_angle) * a.orbit_radius;
        a.pos = vec3(x, y, 0.0f);
        // face the direction of travel (tangent of the circle)
        a.yaw = a.orbit_angle + (a.orbit_speed > 0.0f ? 1.5708f : -1.5708f);
        // fake health that slowly changes so the bars move
        a.health = 55.0f + 45.0f * sin(g_time * 0.4f + float(i));
    }
}

// ---------------------------------------------------------------------------
// Small vector helpers
// ---------------------------------------------------------------------------
float dot3(vec3 a, vec3 b) { return float(a.x * b.x + a.y * b.y + a.z * b.z); }

vec3 cross3(vec3 a, vec3 b) {
    return vec3(float(a.y * b.z - a.z * b.y),
                float(a.z * b.x - a.x * b.z),
                float(a.x * b.y - a.y * b.x));
}

vec3 norm3(vec3 v) {
    float len = sqrt(dot3(v, v));
    if (len < 0.0001f) return vec3(0.0f, 0.0f, 0.0f);
    return vec3(float(v.x) / len, float(v.y) / len, float(v.z) / len);
}

vec3 sub3(vec3 a, vec3 b) { return vec3(float(a.x - b.x), float(a.y - b.y), float(a.z - b.z)); }

// ---------------------------------------------------------------------------
// Camera + world-to-screen
// ---------------------------------------------------------------------------
void update_camera(float dt) {
    g_cam_angle += dt * float(ui::get(sl_cam_speed)) / 100.0f;

    g_cam_pos = vec3(cos(g_cam_angle) * 2200.0f, sin(g_cam_angle) * 2200.0f, 700.0f);
    vec3 target = vec3(200.0f, 0.0f, 80.0f);

    g_cam_fwd = norm3(sub3(target, g_cam_pos));
    g_cam_right = norm3(cross3(g_cam_fwd, vec3(0.0f, 0.0f, 1.0f)));
    g_cam_up = cross3(g_cam_right, g_cam_fwd);

    vec2 vp = render::get_viewport_size();
    g_screen_w = float(vp.x);
    g_screen_h = float(vp.y);

    float fov_deg = float(ui::get(sl_fov));
    g_focal = (g_screen_w * 0.5f) / tan(fov_deg * 0.5f * 3.14159265f / 180.0f);
}

// Classic perspective projection: transform into camera space,
// divide by depth, scale by focal length, offset to screen center.
bool world_to_screen(vec3 world, vec2 &out screen) {
    vec3 d = sub3(world, g_cam_pos);
    float z = dot3(d, g_cam_fwd);
    if (z < 1.0f) return false; // behind the camera

    float x = dot3(d, g_cam_right);
    float y = dot3(d, g_cam_up);

    screen = vec2(g_screen_w * 0.5f + (x / z) * g_focal,
                  g_screen_h * 0.5f - (y / z) * g_focal);
    return true;
}

// ---------------------------------------------------------------------------
// Drawing
// ---------------------------------------------------------------------------
void draw_grid() {
    float extent = 2000.0f;
    float step = 250.0f;
    for (float v = -extent; v <= extent + 0.1f; v += step) {
        vec2 a, b;
        if (world_to_screen(vec3(v, -extent, 0.0f), a) && world_to_screen(vec3(v, extent, 0.0f), b))
            render::draw_line(float(a.x), float(a.y), float(b.x), float(b.y), 90, 90, 110, 120, 1.0f);
        if (world_to_screen(vec3(-extent, v, 0.0f), a) && world_to_screen(vec3(extent, v, 0.0f), b))
            render::draw_line(float(a.x), float(a.y), float(b.x), float(b.y), 90, 90, 110, 120, 1.0f);
    }
}

// Rotate a point from the actor's local space into world space.
vec3 local_to_world(sim_actor@ a, float lx, float ly, float lz) {
    float c = cos(a.yaw);
    float s = sin(a.yaw);
    return vec3(float(a.pos.x) + lx * c - ly * s,
                float(a.pos.y) + lx * s + ly * c,
                lz);
}

void draw_skeleton(sim_actor@ a, color col) {
    float swing = sin(a.walk_phase) * 18.0f;

    // 16 points in the order draw_skel_segments expects
    array<vec3> local = {
        vec3(0, 0, 172),               // 0 head
        vec3(0, 0, 155),               // 1 neck
        vec3(0, 0, 130),               // 2 chest
        vec3(0, 0, 95),                // 3 pelvis
        vec3(0, -20, 150),             // 4 L shoulder
        vec3(swing, -25, 122),         // 5 L elbow
        vec3(swing * 1.5f, -27, 96),   // 6 L hand
        vec3(0, 20, 150),              // 7 R shoulder
        vec3(-swing, 25, 122),         // 8 R elbow
        vec3(-swing * 1.5f, 27, 96),   // 9 R hand
        vec3(0, -10, 95),              // 10 L hip
        vec3(-swing, -11, 52),         // 11 L knee
        vec3(-swing * 1.4f, -12, 4),   // 12 L foot
        vec3(0, 10, 95),               // 13 R hip
        vec3(swing, 11, 52),           // 14 R knee
        vec3(swing * 1.4f, 12, 4)      // 15 R foot
    };

    array<vec2> pts(16);
    for (uint i = 0; i < 16; i++) {
        vec2 s;
        vec3 w = local_to_world(a, float(local[i].x), float(local[i].y), float(local[i].z));
        if (world_to_screen(w, s)) pts[i] = s;
        else pts[i] = vec2(0, 0); // (0,0) is skipped by the renderer
    }

    render::draw_skel_segments(pts, col.r, col.g, col.b, col.a, 1.5f,
                               true, 0, 0, 0, 160, 3.0f);
}

void draw_actor(sim_actor@ a) {
    float dist_m = sqrt(dot3(sub3(a.pos, g_cam_pos), sub3(a.pos, g_cam_pos))) / 100.0f;
    if (dist_m > float(ui::get(sl_max_dist))) return;

    vec2 feet, head;
    if (!world_to_screen(a.pos, feet)) return;
    if (!world_to_screen(vec3(float(a.pos.x), float(a.pos.y), 185.0f), head)) return;

    float h = float(feet.y - head.y);
    if (h < 4.0f) return;
    float w = h * 0.45f;
    float x = float(feet.x) - w * 0.5f;
    float y = float(head.y);

    color col = ui::get(a.team == 0 ? col_team_a : col_team_b);

    if (ui::get(cb_snaplines)) {
        render::draw_line(g_screen_w * 0.5f, g_screen_h, float(feet.x), float(feet.y),
                          col.r, col.g, col.b, 140, 1.0f);
    }

    if (ui::get(cb_boxes)) {
        int style_idx = int(ui::get(cmb_box_style));
        box_style style = box_style::OUTLINED;
        if (style_idx == 1) style = box_style::CORNERED;
        else if (style_idx == 2) style = box_style::FILLED_OUTLINED;

        if (style == box_style::FILLED_OUTLINED)
            render::draw_box(int(x), int(y), int(w), int(h), col.r, col.g, col.b, 60, style, 0.0f);
        else
            render::draw_box(int(x), int(y), int(w), int(h), col.r, col.g, col.b, col.a, style, 0.25f);
    }

    if (ui::get(cb_skeleton)) {
        draw_skeleton(a, ui::get(col_skeleton));
    }

    if (ui::get(cb_health)) {
        float frac = a.health / 100.0f;
        if (frac < 0.0f) frac = 0.0f;
        if (frac > 1.0f) frac = 1.0f;
        int bar_x = int(x) - 6;
        int fill_h = int(h * frac);
        int r = int(255.0f * (1.0f - frac));
        int g = int(255.0f * frac);
        render::draw_rect_filled(bar_x - 1, int(y) - 1, 4, int(h) + 2, 0, 0, 0, 180);
        render::draw_rect_filled(bar_x, int(y + h) - fill_h, 2, fill_h, r, g, 40, 255);
    }

    if (ui::get(cb_names)) {
        vec2 ts = render::calculate_text_size(a.name);
        render::draw_text_outlined(int(float(feet.x) - float(ts.x) * 0.5f), int(y - float(ts.y) - 2.0f),
                                   a.name, 255, 255, 255, 255);
    }

    if (ui::get(cb_distance)) {
        string txt = int(dist_m) + "m";
        vec2 ts = render::calculate_text_size(txt);
        render::draw_text_outlined(int(float(feet.x) - float(ts.x) * 0.5f), int(y + h + 2.0f),
                                   txt, 200, 200, 200, 255);
    }
}

void draw_watermark() {
    string txt = "Overlay demo - simulated scene | " + int(render::get_fps()) + " fps";
    vec2 ts = render::calculate_text_size(txt);
    render::draw_rect_filled(10, 10, int(ts.x) + 16, int(ts.y) + 10, 15, 15, 20, 200);
    render::draw_hue_bar(10, 10, int(ts.x) + 16, 2, 255, 255, 255, 255);
    render::draw_text(18, 16, txt, 255, 255, 255, 255);
}

// ---------------------------------------------------------------------------
// Render callback
// ---------------------------------------------------------------------------
void render_tick() {
    if (!ui::get(cb_enabled)) return;

    float dt = render::get_frametime();
    if (dt > 0.1f) dt = 0.1f; // avoid huge jumps after a stall

    update_scene(dt);
    update_camera(dt);

    if (ui::get(cb_grid)) draw_grid();

    for (uint i = 0; i < g_actors.length(); i++)
        draw_actor(g_actors[i]);

    draw_watermark();
}

// ---------------------------------------------------------------------------
// Menu
// ---------------------------------------------------------------------------
void build_menu() {
    ui::config_path("overlay_demo_school");

    ui::add_tab("Overlay Demo");

    ui::add_category("Visuals", category_pos::left_full);
    cb_enabled   = ui::add_checkbox("Enabled", true);
    cb_boxes     = ui::add_checkbox("Boxes", true);
    cmb_box_style = ui::add_combobox("Box style", {"Outlined", "Cornered", "Filled"}, 0);
    cb_names     = ui::add_checkbox("Names", true);
    cb_health    = ui::add_checkbox("Health bars", true);
    cb_distance  = ui::add_checkbox("Distance", true);
    cb_skeleton  = ui::add_checkbox("Skeleton", true);
    col_skeleton = ui::add_color_picker(cb_skeleton, 255, 255, 255, 255);
    cb_snaplines = ui::add_checkbox("Snaplines", false);
    sl_max_dist  = ui::add_slider("Max distance", 60, 5, 100, 1, "m");

    ui::add_category("Scene", category_pos::right_full);
    cb_grid      = ui::add_checkbox("Ground grid", true);
    col_team_a   = ui::add_color_picker("Team A color", 80, 170, 255, 255);
    col_team_b   = ui::add_color_picker("Team B color", 255, 90, 90, 255);
    sl_cam_speed = ui::add_slider("Camera orbit speed", 15, 0, 100, 1, "%");
    sl_fov       = ui::add_slider("Field of view", 90, 60, 120, 1, "deg");
}

bool main() {
    build_menu();
    build_scene();
    on_render(@render_tick);
    print("overlay_demo loaded: drawing a simulated scene");
    return true;
}
