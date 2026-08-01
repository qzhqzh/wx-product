<script setup>
import { computed, onMounted, ref } from "vue";
import {
  Check,
  CircleCheck,
  Download,
  FolderChecked,
  Upload,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  releaseId: { type: String, required: true },
});

const release = ref(null);
const loading = ref(true);
const busyAction = ref("");
const uploadInput = ref(null);
const uploadType = ref("build_package");
const showSubmission = ref(false);
const submission = ref({
  id: null,
  platform_audit_id: "",
  status: "submitted",
  rejection_reason: "",
  notes: "",
});

const steps = [
  ["draft", "PRD"],
  ["prd_approved", "范围确认"],
  ["developing", "开发"],
  ["build_ready", "构建"],
  ["experience_review", "体验版"],
  ["compliance_review", "隐私合规"],
  ["qa_review", "发布 QA"],
  ["export_ready", "审核包"],
  ["submitted", "微信审核"],
  ["approved", "审核通过"],
  ["released", "已发布"],
];

const activeStep = computed(() => {
  if (!release.value) return 0;
  if (release.value.status === "rework") return 4;
  const index = steps.findIndex(([state]) => state === release.value.status);
  return Math.max(0, index);
});
const currentArtifacts = computed(
  () => release.value?.artifacts?.filter((artifact) => artifact.is_current) || [],
);
const buildArtifact = computed(() =>
  currentArtifacts.value.find(
    (artifact) => artifact.artifact_type === "build_package",
  ),
);
const qrArtifact = computed(() =>
  currentArtifacts.value.find(
    (artifact) => artifact.artifact_type === "experience_qr",
  ),
);
const screenshots = computed(() =>
  currentArtifacts.value.filter(
    (artifact) => artifact.artifact_type === "screenshot",
  ),
);
const checklistDone = computed(
  () =>
    release.value?.checklist_items?.filter((item) => item.is_completed).length ||
    0,
);
const testPassed = computed(
  () =>
    release.value?.test_cases?.filter((item) => item.result === "passed").length ||
    0,
);
const latestValidation = computed(() => release.value?.latest_validation);
const latestExport = computed(() => release.value?.latest_export);
const latestSubmission = computed(() => release.value?.latest_submission);

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
    release.value = await api(
      `/api/v1/mini-program/releases/${props.releaseId}/`,
    );
  } catch (error) {
    ElMessage.error(error.message);
  } finally {
    loading.value = false;
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

function prepareDemo() {
  return runAction(
    "prepare",
    () =>
      api(
        `/api/v1/mini-program/releases/${props.releaseId}/prepare-demo/`,
        { method: "POST", body: "{}" },
      ),
    "演示构建、体验码、截图、清单和测试案例已准备。",
  );
}

async function uploadArtifact(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  body.append("artifact_type", uploadType.value);
  body.append("label", file.name);
  await runAction(
    "upload",
    () =>
      api(`/api/v1/mini-program/releases/${props.releaseId}/artifacts/`, {
        method: "POST",
        body,
      }),
    "版本产物已上传。",
  );
  event.target.value = "";
}

function toggleChecklist(item) {
  return runAction(
    `check-${item.id}`,
    () =>
      api(
        `/api/v1/mini-program/releases/${props.releaseId}/checklist/${item.id}/`,
        {
          method: "PATCH",
          body: JSON.stringify({ is_completed: !item.is_completed }),
        },
      ),
    item.is_completed ? "已重新打开检查项。" : "检查项已完成。",
  );
}

function saveTestCase(testCase) {
  return runAction(
    `test-${testCase.id}`,
    () =>
      api(
        `/api/v1/mini-program/releases/${props.releaseId}/tests/${testCase.id}/`,
        {
          method: "PATCH",
          body: JSON.stringify({
            result: testCase.result,
            actual_result: testCase.actual_result,
          }),
        },
      ),
    "测试结果已保存。",
  );
}

function validateRelease() {
  return runAction(
    "validate",
    () =>
      api(`/api/v1/mini-program/releases/${props.releaseId}/validate/`, {
        method: "POST",
        body: "{}",
      }),
    "小程序发布 QA 已完成。",
  );
}

function exportRelease() {
  return runAction(
    "export",
    () =>
      api(`/api/v1/mini-program/releases/${props.releaseId}/export/`, {
        method: "POST",
        body: "{}",
      }),
    "微信审核包已生成。",
  );
}

function openSubmission() {
  submission.value = latestSubmission.value
    ? {
        id: latestSubmission.value.id,
        platform_audit_id: latestSubmission.value.platform_audit_id || "",
        status: latestSubmission.value.status,
        rejection_reason: latestSubmission.value.rejection_reason || "",
        notes: latestSubmission.value.notes || "",
      }
    : {
        id: null,
        platform_audit_id: "",
        status: "submitted",
        rejection_reason: "",
        notes: "",
      };
  showSubmission.value = true;
}

async function saveSubmission() {
  const isUpdate = Boolean(submission.value.id);
  await runAction(
    "submission",
    () =>
      api(`/api/v1/mini-program/releases/${props.releaseId}/submissions/`, {
        method: isUpdate ? "PATCH" : "POST",
        body: JSON.stringify(submission.value),
      }),
    isUpdate ? "微信审核/发布状态已更新。" : "微信人工提审记录已保存。",
  );
  showSubmission.value = false;
}

function artifactAccept() {
  if (uploadType.value === "build_package") return ".zip,application/zip";
  if (uploadType.value === "privacy_document") return ".pdf,.txt,.md";
  return ".png,.jpg,.jpeg,image/png,image/jpeg";
}

onMounted(refresh);
</script>

<template>
  <div v-loading="loading" class="wb product-wb">
    <template v-if="release">
      <header class="wb-header">
        <div>
          <div class="wb-title-line">
            <h1>{{ release.name }} {{ release.version }}</h1>
            <el-tag effect="plain" round>{{ release.status_label }}</el-tag>
          </div>
          <p>
            {{ release.release_type_label }} ·
            {{ checklistDone }}/{{ release.checklist_items.length }} 项检查完成 ·
            {{ testPassed }}/{{ release.test_cases.length }} 个案例通过
          </p>
        </div>
        <div class="wb-header-actions artifact-upload-actions">
          <el-select v-model="uploadType" aria-label="上传产物类型" style="width: 150px">
            <el-option label="构建包" value="build_package" />
            <el-option label="体验二维码" value="experience_qr" />
            <el-option label="页面截图" value="screenshot" />
            <el-option label="隐私文档" value="privacy_document" />
            <el-option label="测试证据" value="test_evidence" />
          </el-select>
          <el-button
            :icon="Upload"
            :loading="busyAction === 'upload'"
            @click="uploadInput?.click()"
          >
            上传产物
          </el-button>
          <input
            ref="uploadInput"
            class="sr-only"
            type="file"
            :accept="artifactAccept()"
            @change="uploadArtifact"
          />
          <el-button
            type="primary"
            :icon="FolderChecked"
            :disabled="!['draft', 'prd_approved', 'rework'].includes(release.status)"
            :loading="busyAction === 'prepare'"
            @click="prepareDemo"
          >
            准备演示版本
          </el-button>
        </div>
      </header>

      <section class="wb-flow product-flow" aria-label="小程序发布进度">
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
          <section>
            <div class="wb-section-heading">
              <div>
                <h2>当前版本产物</h2>
                <p>构建包和体验码保留历史版本；审核包只引用标记为当前的版本。</p>
              </div>
            </div>
            <div class="release-artifacts">
              <div class="artifact-primary">
                <div class="artifact-file">
                  <FolderChecked />
                  <div>
                    <strong>{{ buildArtifact?.label || "尚未上传构建包" }}</strong>
                    <span v-if="buildArtifact">{{ buildArtifact.asset.original_name }} · {{ Math.ceil(buildArtifact.asset.size_bytes / 1024) }}KB</span>
                    <span v-else>支持 ZIP，最大体积由当前规则集控制</span>
                  </div>
                  <a v-if="buildArtifact" :href="buildArtifact.asset.url">查看</a>
                </div>
                <div class="experience-qr">
                  <img v-if="qrArtifact" :src="qrArtifact.asset.url" alt="体验版二维码" />
                  <div v-else class="artifact-placeholder">体验码</div>
                  <span>{{ qrArtifact?.label || "尚未上传体验二维码" }}</span>
                </div>
              </div>
              <div class="screenshot-strip">
                <figure v-for="artifact in screenshots" :key="artifact.id">
                  <img :src="artifact.asset.url" :alt="artifact.label" loading="lazy" />
                  <figcaption>{{ artifact.label }}</figcaption>
                </figure>
                <div v-if="!screenshots.length" class="artifact-placeholder">
                  至少上传两张核心页面审核截图
                </div>
              </div>
            </div>
          </section>

          <section class="product-section">
            <div class="section-header">
              <h2 class="section-title">发布检查清单</h2>
              <span class="section-meta">{{ checklistDone }}/{{ release.checklist_items.length }} 已完成</span>
            </div>
            <div class="checklist-list">
              <button
                v-for="item in release.checklist_items"
                :key="item.id"
                type="button"
                class="checklist-item"
                :class="{ 'is-complete': item.is_completed }"
                :aria-pressed="item.is_completed"
                @click="toggleChecklist(item)"
              >
                <span class="check-mark"><Check v-if="item.is_completed" /></span>
                <span><strong>{{ item.title }}</strong><small>{{ item.category_label }}<template v-if="item.is_required"> · 必做</template></small></span>
              </button>
            </div>
          </section>

          <section class="product-section">
            <div class="section-header">
              <h2 class="section-title">发布测试案例</h2>
              <span class="section-meta">{{ testPassed }}/{{ release.test_cases.length }} 通过</span>
            </div>
            <article v-for="testCase in release.test_cases" :key="testCase.id" class="test-case-row">
              <div>
                <strong>{{ testCase.name }}</strong>
                <span>{{ testCase.expected_result }}</span>
              </div>
              <el-input v-model="testCase.actual_result" placeholder="记录实际结果" />
              <el-select v-model="testCase.result" aria-label="测试结果">
                <el-option label="待执行" value="pending" />
                <el-option label="通过" value="passed" />
                <el-option label="失败" value="failed" />
                <el-option label="阻塞" value="blocked" />
              </el-select>
              <el-button
                size="small"
                :loading="busyAction === `test-${testCase.id}`"
                @click="saveTestCase(testCase)"
              >
                保存
              </el-button>
            </article>
          </section>
        </main>

        <aside class="wb-sidebar">
          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>版本范围</h2></div>
            <div class="side-summary">
              <strong>{{ release.service_category || "未设置服务类目" }}</strong>
              <span>{{ release.prd_summary }}</span>
            </div>
            <div class="side-summary">
              <strong>隐私边界</strong>
              <span>{{ release.privacy_summary || "尚未填写隐私处理摘要" }}</span>
            </div>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>发布 QA</h2></div>
            <div
              v-if="latestValidation"
              class="qa-result"
              :class="{ 'is-passed': latestValidation.passed }"
            >
              <CircleCheck v-if="latestValidation.passed" />
              <Warning v-else />
              <div>
                <strong>{{ latestValidation.passed ? "检查通过" : "需要返修" }}</strong>
                <span>{{ latestValidation.error_count }} 错误 · {{ latestValidation.warning_count }} 提示</span>
              </div>
            </div>
            <p v-else class="side-empty">验证构建、截图、体验码、隐私清单和全部测试结果。</p>
            <ul v-if="latestValidation?.issues?.length" class="issue-list">
              <li v-for="issue in latestValidation.issues" :key="issue.id">
                <Warning />
                <div><strong>{{ issue.message }}</strong><span>{{ issue.remediation }}</span></div>
              </li>
            </ul>
            <el-button
              class="side-action"
              :loading="busyAction === 'validate'"
              @click="validateRelease"
            >
              运行发布 QA
            </el-button>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>审核包与微信状态</h2></div>
            <a v-if="latestExport" class="export-link" :href="latestExport.download_url">
              <Download />
              <div><strong>下载微信审核包</strong><span>{{ latestExport.checksum_sha256.slice(0, 12) }}…</span></div>
            </a>
            <p v-else class="side-empty">QA 通过后生成包含构建、截图、隐私和测试报告的 ZIP。</p>
            <el-button
              class="side-action"
              :loading="busyAction === 'export'"
              @click="exportRelease"
            >
              生成审核包
            </el-button>
            <el-button
              class="side-action"
              :disabled="!latestExport"
              @click="openSubmission"
            >
              {{ latestSubmission ? "更新审核/发布状态" : "登记人工提审" }}
            </el-button>
          </section>
        </aside>
      </div>
    </template>

    <el-dialog v-model="showSubmission" title="微信小程序审核与发布记录" width="min(540px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="微信审核编号"><el-input v-model="submission.platform_audit_id" /></el-form-item>
        <el-form-item label="状态">
          <el-select v-model="submission.status" style="width: 100%">
            <el-option label="已提交" value="submitted" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="审核通过" value="approved" />
            <el-option label="已发布" value="released" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="submission.status === 'rejected'" label="驳回原因">
          <el-input v-model="submission.rejection_reason" type="textarea" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="submission.notes" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showSubmission = false">取消</el-button><el-button type="primary" @click="saveSubmission">保存</el-button></template>
    </el-dialog>
  </div>
</template>
