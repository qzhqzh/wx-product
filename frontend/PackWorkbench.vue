<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  Check,
  CircleCheck,
  Clock,
  Download,
  MagicStick,
  Refresh,
  Select,
  Upload,
  VideoPlay,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  packId: { type: String, required: true },
});

const pack = ref(null);
const loading = ref(true);
const busyAction = ref("");
const textProvider = ref("local");
const imageProvider = ref("local");
const selectedPromptPresetIds = ref([]);
const promptDrafts = ref({});
const showSubmission = ref(false);
const submission = ref({
  id: null,
  platform_work_id: "",
  status: "submitted",
  submitted_at: "",
  scheduled_publish_at: "",
  rejection_reason: "",
  notes: "",
});
const uploadInputs = new Map();
let pollingTimer = null;

const steps = [
  ["draft", "Brief"],
  ["brief_approved", "语义策划"],
  ["generating", "素材生成"],
  ["creative_review", "创意审稿"],
  ["processing", "媒体处理"],
  ["qa_review", "QA"],
  ["export_ready", "投稿包"],
  ["submitted", "微信审核"],
  ["published", "已上架"],
];

const activeStep = computed(() => {
  if (!pack.value) return 0;
  if (pack.value.status === "rework") return 3;
  const index = steps.findIndex(([state]) => state === pack.value.status);
  return Math.max(0, index);
});

const runningJobs = computed(
  () =>
    pack.value?.jobs?.filter((job) =>
      ["queued", "running"].includes(job.status),
    ) || [],
);

const selectedCount = computed(
  () =>
    pack.value?.items?.filter((item) => Boolean(item.selected_asset)).length || 0,
);

const approvedCount = computed(
  () => pack.value?.items?.filter((item) => item.is_approved).length || 0,
);

const canGenerateAll = computed(
  () => pack.value?.items?.length > 0 && runningJobs.value.length === 0,
);

const latestValidation = computed(() => pack.value?.latest_validation);
const latestExport = computed(() => pack.value?.latest_export);
const latestSubmission = computed(() => pack.value?.latest_submission);

function csrfToken() {
  return document.querySelector('meta[name="csrf-token"]')?.content || "";
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set("X-CSRFToken", csrfToken());
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    credentials: "same-origin",
    ...options,
    headers,
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || "请求失败，请稍后重试。");
  }
  return payload;
}

async function refresh({ silent = false } = {}) {
  if (!silent) loading.value = true;
  try {
    pack.value = await api(`/api/v1/packs/${props.packId}/`);
    selectedPromptPresetIds.value = pack.value.available_prompt_presets
      .filter((preset) => preset.selected)
      .map((preset) => preset.id);
    promptDrafts.value = Object.fromEntries(
      pack.value.items.map((item) => [item.id, item.prompt || ""]),
    );
    schedulePolling();
  } catch (error) {
    if (!silent) ElMessage.error(error.message);
  } finally {
    loading.value = false;
  }
}

function schedulePolling() {
  if (pollingTimer) window.clearTimeout(pollingTimer);
  if (runningJobs.value.length) {
    pollingTimer = window.setTimeout(async () => {
      await refresh({ silent: true });
    }, 1800);
  }
}

async function runAction(name, callback, successMessage) {
  busyAction.value = name;
  try {
    await callback();
    if (successMessage) ElMessage.success(successMessage);
    await refresh({ silent: true });
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    busyAction.value = "";
  }
}

function planPack() {
  return runAction(
    "plan",
    () =>
      api(`/api/v1/packs/${props.packId}/plan/`, {
        method: "POST",
        body: JSON.stringify({ provider: textProvider.value }),
      }),
    "语义策划任务已进入队列。",
  );
}

function generateAll() {
  return runAction(
    "all",
    () =>
      api(`/api/v1/packs/${props.packId}/generate/`, {
        method: "POST",
        body: JSON.stringify({ provider: imageProvider.value }),
      }),
    "全部候选已进入生成队列。",
  );
}

function generateItem(item) {
  return runAction(
    `item-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/generate/`, {
        method: "POST",
        body: JSON.stringify({ provider: imageProvider.value }),
      }),
    `“${item.meaning}”已进入生成队列。`,
  );
}

function savePromptPresets() {
  return runAction(
    "prompt-presets",
    () =>
      api(`/api/v1/packs/${props.packId}/prompt-presets/`, {
        method: "PATCH",
        body: JSON.stringify({ preset_ids: selectedPromptPresetIds.value }),
      }),
    "专辑提示词方案已保存。",
  );
}

function saveItemPrompt(item) {
  return runAction(
    `prompt-save-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/prompt/`, {
        method: "PATCH",
        body: JSON.stringify({ prompt: promptDrafts.value[item.id] }),
      }),
    `“${item.meaning}”的提示词已保存。`,
  );
}

function optimizeItemPrompt(item) {
  return runAction(
    `prompt-optimize-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/prompt/`, {
        method: "POST",
        body: JSON.stringify({
          provider: textProvider.value,
          prompt: promptDrafts.value[item.id],
        }),
      }),
    `“${item.meaning}”的提示词优化任务已进入队列。`,
  );
}

function selectAsset(item, asset) {
  return runAction(
    `select-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/select/`, {
        method: "POST",
        body: JSON.stringify({ asset_id: asset.id }),
      }),
    "已选择成品版本。",
  );
}

function approveItem(item) {
  return runAction(
    `approve-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/approve/`, {
        method: "POST",
        body: JSON.stringify({ approved: !item.is_approved }),
      }),
    item.is_approved ? "已撤销确认。" : "该表情已通过创意确认。",
  );
}

function generateFrames(item) {
  return runAction(
    `frames-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/frames/`, {
        method: "POST",
        body: JSON.stringify({ frame_count: 6 }),
      }),
    "序列帧与 GIF 合成任务已进入队列。",
  );
}

function moveFrame(item, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= item.frames.length) return;
  const frames = [...item.frames];
  [frames[index], frames[target]] = [frames[target], frames[index]];
  item.frames = frames;
}

function saveSequence(item) {
  return runAction(
    `sequence-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/sequence/`, {
        method: "PATCH",
        body: JSON.stringify({
          frames: item.frames.map((frame) => ({
            id: frame.id,
            duration_ms: Number(frame.duration_ms),
          })),
        }),
      }),
    "时间轴已保存，正在重新合成 GIF。",
  );
}

function validatePack() {
  return runAction(
    "validate",
    () =>
      api(`/api/v1/packs/${props.packId}/validate/`, {
        method: "POST",
        body: "{}",
      }),
    "QA 检查已完成。",
  );
}

function exportPack() {
  return runAction(
    "export",
    () =>
      api(`/api/v1/packs/${props.packId}/export/`, {
        method: "POST",
        body: "{}",
      }),
    "投稿包已生成。",
  );
}

function triggerUpload(item) {
  uploadInputs.get(item.id)?.click();
}

async function uploadItem(item, event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  await runAction(
    `upload-${item.id}`,
    () =>
      api(`/api/v1/packs/${props.packId}/items/${item.id}/upload/`, {
        method: "POST",
        body: formData,
      }),
    "素材已上传并规范化。",
  );
  event.target.value = "";
}

function bindUploadInput(itemId, element) {
  if (element) uploadInputs.set(itemId, element);
}

function openSubmission() {
  if (latestSubmission.value) {
    submission.value = {
      id: latestSubmission.value.id,
      platform_work_id: latestSubmission.value.platform_work_id || "",
      status: latestSubmission.value.status,
      submitted_at: latestSubmission.value.submitted_at || "",
      scheduled_publish_at: latestSubmission.value.scheduled_publish_at || "",
      rejection_reason: latestSubmission.value.rejection_reason || "",
      notes: latestSubmission.value.notes || "",
    };
  } else {
    submission.value = {
      id: null,
      platform_work_id: "",
      status: "submitted",
      submitted_at: "",
      scheduled_publish_at: "",
      rejection_reason: "",
      notes: "",
    };
  }
  showSubmission.value = true;
}

async function submitRecord() {
  const isUpdate = Boolean(submission.value.id);
  await runAction(
    "submission",
    () =>
      api(`/api/v1/packs/${props.packId}/submissions/`, {
        method: isUpdate ? "PATCH" : "POST",
        body: JSON.stringify({
          ...submission.value,
          submitted_at: submission.value.submitted_at || null,
          scheduled_publish_at: submission.value.scheduled_publish_at || null,
        }),
      }),
    isUpdate ? "平台反馈已更新。" : "人工投稿记录已保存。",
  );
  showSubmission.value = false;
}

function assetSelected(item, asset) {
  return item.selected_asset?.id === asset.id;
}

function jobTone(status) {
  if (status === "succeeded") return "success";
  if (["failed", "blocked"].includes(status)) return "danger";
  if (status === "running") return "warning";
  return "info";
}

function issueIcon(severity) {
  return severity === "error" ? Warning : Clock;
}

function submissionStatusLabel(status) {
  return {
    submitted: "已提交",
    in_review: "审核中",
    rejected: "已驳回",
    approved: "审核通过",
    published: "已上架",
  }[status] || status;
}

onMounted(refresh);
onBeforeUnmount(() => {
  if (pollingTimer) window.clearTimeout(pollingTimer);
});
</script>

<template>
  <div v-loading="loading" class="wb">
    <template v-if="pack">
      <header class="wb-header">
        <div>
          <div class="wb-title-line">
            <h1>{{ pack.name }}</h1>
            <el-tag effect="plain" round>{{ pack.status_label }}</el-tag>
          </div>
          <p>
            {{ pack.media_type_label }} · {{ pack.target_count }} 个目标 ·
            {{ selectedCount }} 个已选 · {{ approvedCount }} 个已确认
          </p>
        </div>
        <div class="wb-header-actions">
          <el-select
            v-model="textProvider"
            aria-label="策划与提示词模型"
            style="width: 168px"
          >
            <el-option label="本地策划" value="local" />
            <el-option label="OpenAI" value="openai" />
            <el-option label="Qwen 3.7 Plus" value="qwen" />
          </el-select>
          <el-select
            v-model="imageProvider"
            aria-label="图像生成模型"
            style="width: 150px"
          >
            <el-option label="本地生图" value="local" />
            <el-option label="OpenAI 生图" value="openai" />
          </el-select>
          <el-button
            :icon="MagicStick"
            :loading="busyAction === 'plan'"
            @click="planPack"
          >
            生成语义
          </el-button>
          <el-button
            type="primary"
            :icon="Refresh"
            :disabled="!canGenerateAll"
            :loading="busyAction === 'all'"
            @click="generateAll"
          >
            批量生成
          </el-button>
        </div>
      </header>

      <section class="wb-flow" aria-label="专辑生产进度">
        <div
          v-for="([state, label], index) in steps"
          :key="state"
          class="wb-step"
          :class="{
            'is-done': index < activeStep,
            'is-current': index === activeStep,
          }"
        >
          <span class="wb-step-dot">
            <Check v-if="index < activeStep" />
            <span v-else>{{ index + 1 }}</span>
          </span>
          <span>{{ label }}</span>
        </div>
      </section>

      <div class="wb-layout">
        <main class="wb-items">
          <div class="wb-section-heading">
            <div>
              <h2>语义与素材</h2>
              <p>每项独立生成、选稿和返修；失败不会覆盖其他已确认版本。</p>
            </div>
          </div>

          <div v-if="!pack.items.length" class="wb-empty">
            <MagicStick />
            <strong>先生成聊天语义矩阵</strong>
            <p>系统会按目标数量建立含义词、文案、动作与图像提示词。</p>
            <el-button type="primary" @click="planPack">生成语义矩阵</el-button>
          </div>

          <article
            v-for="item in pack.items"
            :key="item.id"
            class="emoji-row"
          >
            <div class="emoji-brief">
              <span class="emoji-order">{{ String(item.order).padStart(2, "0") }}</span>
              <div>
                <h3>{{ item.meaning }}</h3>
                <p class="emoji-copy">{{ item.copy_text || "无文案" }}</p>
                <p class="emoji-action">{{ item.action }}</p>
              </div>
              <el-tag
                v-if="item.is_approved"
                type="success"
                effect="light"
                round
              >
                已确认
              </el-tag>
            </div>

            <div class="candidate-strip">
              <button
                v-for="asset in item.candidates"
                :key="asset.id"
                class="candidate"
                :class="{ 'is-selected': assetSelected(item, asset) }"
                type="button"
                :aria-pressed="assetSelected(item, asset)"
                :title="`${asset.original_name} · ${asset.width}×${asset.height}`"
                @click="selectAsset(item, asset)"
              >
                <img :src="asset.url" :alt="`${item.meaning}候选`" loading="lazy" />
                <span v-if="assetSelected(item, asset)" class="candidate-check">
                  <CircleCheck />
                </span>
                <span class="candidate-meta">{{ asset.kind }}</span>
              </button>
              <button
                class="candidate candidate-add"
                type="button"
                @click="triggerUpload(item)"
              >
                <Upload />
                <span>上传</span>
              </button>
              <input
                :ref="(el) => bindUploadInput(item.id, el)"
                class="sr-only"
                type="file"
                accept=".png,.jpg,.jpeg,.gif,image/png,image/jpeg,image/gif"
                @change="uploadItem(item, $event)"
              />
            </div>

            <div class="emoji-actions">
              <el-button
                size="small"
                :icon="MagicStick"
                :loading="busyAction === `item-${item.id}`"
                @click="generateItem(item)"
              >
                再生成
              </el-button>
              <el-button
                v-if="pack.media_type === 'dynamic'"
                size="small"
                :icon="VideoPlay"
                :disabled="!item.selected_asset"
                :loading="busyAction === `frames-${item.id}`"
                @click="generateFrames(item)"
              >
                {{ item.frames.length ? "重做动效" : "生成动效" }}
              </el-button>
              <el-button
                size="small"
                :type="item.is_approved ? 'default' : 'success'"
                :icon="Select"
                :disabled="!item.selected_asset"
                :loading="busyAction === `approve-${item.id}`"
                @click="approveItem(item)"
              >
                {{ item.is_approved ? "撤销确认" : "确认" }}
              </el-button>
            </div>

            <details class="prompt-inline-editor">
              <summary>
                <span>图像提示词</span>
                <small>{{ promptDrafts[item.id]?.length || 0 }} 字</small>
              </summary>
              <div class="prompt-inline-body">
                <el-input
                  v-model="promptDrafts[item.id]"
                  type="textarea"
                  :rows="4"
                  maxlength="4000"
                  show-word-limit
                  :aria-label="`${item.meaning}图像提示词`"
                />
                <div class="prompt-inline-actions">
                  <el-button
                    size="small"
                    :loading="busyAction === `prompt-save-${item.id}`"
                    @click="saveItemPrompt(item)"
                  >
                    保存修改
                  </el-button>
                  <el-button
                    size="small"
                    type="primary"
                    :loading="busyAction === `prompt-optimize-${item.id}`"
                    @click="optimizeItemPrompt(item)"
                  >
                    用{{ textProvider === "qwen" ? " Qwen" : "策划模型" }}优化
                  </el-button>
                </div>
              </div>
            </details>

            <div v-if="item.frames.length" class="frame-editor">
              <div class="frame-editor-heading">
                <div>
                  <strong>序列帧时间轴</strong>
                  <span>调整顺序与停留时间后重新合成，不会覆盖母帧。</span>
                </div>
                <el-button
                  size="small"
                  :loading="busyAction === `sequence-${item.id}`"
                  @click="saveSequence(item)"
                >
                  保存并合成
                </el-button>
              </div>
              <div class="frame-strip">
                <div
                  v-for="(frame, index) in item.frames"
                  :key="frame.id"
                  class="frame"
                >
                  <span class="frame-index">{{ index + 1 }}</span>
                  <img :src="frame.asset.url" alt="" loading="lazy" />
                  <label>
                    <span class="sr-only">第 {{ index + 1 }} 帧时长</span>
                    <input
                      v-model.number="frame.duration_ms"
                      class="frame-duration"
                      type="number"
                      min="40"
                      max="2000"
                      step="20"
                    />
                    <small>ms</small>
                  </label>
                  <div class="frame-order-actions">
                    <button
                      type="button"
                      :disabled="index === 0"
                      aria-label="前移一帧"
                      @click="moveFrame(item, index, -1)"
                    >
                      ←
                    </button>
                    <button
                      type="button"
                      :disabled="index === item.frames.length - 1"
                      aria-label="后移一帧"
                      @click="moveFrame(item, index, 1)"
                    >
                      →
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </article>
        </main>

        <aside class="wb-sidebar">
          <section class="wb-side-section">
            <div class="wb-side-heading">
              <h2>提示词方案</h2>
              <a href="/products/emoji/prompts/">管理词库</a>
            </div>
            <p class="side-empty">组合基础、风格、构图、质量和负向片段；生成任务会保存本次组合快照。</p>
            <el-select
              v-model="selectedPromptPresetIds"
              multiple
              collapse-tags
              collapse-tags-tooltip
              aria-label="专辑提示词方案"
              placeholder="选择常用提示词"
              style="width: 100%"
            >
              <el-option
                v-for="preset in pack.available_prompt_presets"
                :key="preset.id"
                :label="`${preset.category_label} · ${preset.name}`"
                :value="preset.id"
              />
            </el-select>
            <el-button
              class="side-action"
              :loading="busyAction === 'prompt-presets'"
              @click="savePromptPresets"
            >
              保存提示词方案
            </el-button>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading">
              <h2>质量闸门</h2>
              <el-button
                text
                :icon="Refresh"
                :loading="busyAction === 'validate'"
                @click="validatePack"
              >
                重新检查
              </el-button>
            </div>
            <div v-if="latestValidation" class="qa-summary">
              <div
                class="qa-result"
                :class="{ 'is-passed': latestValidation.passed }"
              >
                <component
                  :is="latestValidation.passed ? CircleCheck : Warning"
                />
                <div>
                  <strong>
                    {{ latestValidation.passed ? "确定性检查通过" : "仍有阻断问题" }}
                  </strong>
                  <span>
                    {{ latestValidation.error_count }} 错误 ·
                    {{ latestValidation.warning_count }} 警告
                  </span>
                </div>
              </div>
              <ul v-if="latestValidation.issues.length" class="issue-list">
                <li
                  v-for="issue in latestValidation.issues"
                  :key="issue.id"
                  :class="`is-${issue.severity}`"
                >
                  <component :is="issueIcon(issue.severity)" />
                  <div>
                    <strong>{{ issue.message }}</strong>
                    <span>{{ issue.remediation }}</span>
                  </div>
                </li>
              </ul>
            </div>
            <div v-else class="side-empty">
              尚未执行 QA。生成并确认素材后，检查数量、格式、尺寸、体积、动效和权利材料。
            </div>
            <el-button
              type="primary"
              :icon="Download"
              :disabled="!latestValidation?.passed"
              :loading="busyAction === 'export'"
              style="width: 100%; margin-top: 12px"
              @click="exportPack"
            >
              生成投稿包
            </el-button>
          </section>

          <section v-if="latestExport" class="wb-side-section">
            <div class="wb-side-heading"><h2>最近导出</h2></div>
            <a class="export-link" :href="latestExport.download_url">
              <Download />
              <div>
                <strong>下载投稿 ZIP</strong>
                <span>{{ latestExport.checksum_sha256.slice(0, 12) }}…</span>
              </div>
            </a>
            <el-button
              style="width: 100%; margin-top: 10px"
              @click="openSubmission"
            >
              {{ latestSubmission ? "更新平台反馈" : "登记人工投稿" }}
            </el-button>
          </section>

          <section v-if="latestSubmission" class="wb-side-section">
            <div class="wb-side-heading">
              <h2>微信平台反馈</h2>
              <el-tag
                :type="latestSubmission.status === 'rejected' ? 'danger' : 'info'"
                effect="light"
              >
                {{ submissionStatusLabel(latestSubmission.status) }}
              </el-tag>
            </div>
            <div class="submission-summary">
              <strong>{{ latestSubmission.platform_work_id || "尚未填写作品编号" }}</strong>
              <span v-if="latestSubmission.rejection_reason">
                {{ latestSubmission.rejection_reason }}
              </span>
              <span v-else>{{ latestSubmission.notes || "等待下一次平台状态更新。" }}</span>
            </div>
            <el-button
              style="width: 100%; margin-top: 10px"
              @click="openSubmission"
            >
              更新状态与反馈
            </el-button>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading">
              <h2>任务队列</h2>
              <el-button text :icon="Refresh" @click="refresh({ silent: true })" />
            </div>
            <ul v-if="pack.jobs.length" class="job-list">
              <li v-for="job in pack.jobs.slice(0, 12)" :key="job.id">
                <el-tag :type="jobTone(job.status)" size="small" effect="light">
                  {{ job.status_label }}
                </el-tag>
                <div>
                  <strong>{{ job.job_type_label }}</strong>
                  <span>{{ job.provider }} · {{ job.model || "待执行" }}</span>
                  <em v-if="job.error_message">{{ job.error_message }}</em>
                </div>
              </li>
            </ul>
            <div v-else class="side-empty">还没有任务记录。</div>
          </section>
        </aside>
      </div>
    </template>

    <el-dialog
      v-model="showSubmission"
      :title="submission.id ? '更新微信平台反馈' : '登记微信人工投稿'"
      width="min(520px, 94vw)"
      destroy-on-close
    >
      <el-form label-position="top">
        <el-form-item label="平台作品编号">
          <el-input v-model="submission.platform_work_id" placeholder="可稍后补充" />
        </el-form-item>
        <el-form-item label="当前状态">
          <el-select v-model="submission.status" style="width: 100%">
            <el-option label="已提交" value="submitted" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="审核通过" value="approved" />
            <el-option label="已上架" value="published" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="submission.status === 'rejected'" label="驳回原因">
          <el-input
            v-model="submission.rejection_reason"
            type="textarea"
            :rows="2"
            placeholder="按平台原文记录，便于定向返修"
          />
        </el-form-item>
        <el-form-item label="备注">
          <el-input
            v-model="submission.notes"
            type="textarea"
            :rows="3"
            placeholder="记录账号、计划上架时间或其他人工步骤"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSubmission = false">取消</el-button>
        <el-button
          type="primary"
          :loading="busyAction === 'submission'"
          @click="submitRecord"
        >
          保存投稿记录
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>
