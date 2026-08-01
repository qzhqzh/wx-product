<script setup>
import { computed, onMounted, ref } from "vue";
import {
  Box,
  Check,
  CircleCheck,
  Download,
  MagicStick,
  Select,
  Upload,
  Warning,
} from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  campaignId: { type: String, required: true },
});

const campaign = ref(null);
const loading = ref(true);
const busyAction = ref("");
const uploadInput = ref(null);
const showSubmission = ref(false);
const showOrder = ref(false);
const showDistribution = ref(false);
const activeOrder = ref(null);
const submission = ref({
  id: null,
  platform_work_id: "",
  status: "submitted",
  rejection_reason: "",
  notes: "",
});
const orderForm = ref({
  platform_order_no: "",
  quantity: 100,
  unit_cost: 0,
  notes: "",
});
const distributionForm = ref({
  channel: "社群发放",
  quantity: 1,
  notes: "",
});

const steps = [
  ["draft", "Brief"],
  ["brief_approved", "Brief 确认"],
  ["designing", "封面设计"],
  ["creative_review", "创意审稿"],
  ["rights_review", "权利审核"],
  ["qa_review", "技术 QA"],
  ["export_ready", "投稿包"],
  ["submitted", "微信审核"],
  ["approved", "审核通过"],
  ["distributing", "发放"],
  ["completed", "完成"],
];

const activeStep = computed(() => {
  if (!campaign.value) return 0;
  if (campaign.value.status === "rework") return 3;
  const index = steps.findIndex(([state]) => state === campaign.value.status);
  return Math.max(0, index);
});
const selectedDesign = computed(() =>
  campaign.value?.designs?.find((design) => design.is_selected),
);
const latestValidation = computed(() => campaign.value?.latest_validation);
const latestExport = computed(() => campaign.value?.latest_export);
const latestSubmission = computed(() => campaign.value?.latest_submission);

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
    campaign.value = await api(
      `/api/v1/red-packet/campaigns/${props.campaignId}/`,
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

function generateDesigns() {
  return runAction(
    "generate",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/generate/`, {
        method: "POST",
        body: "{}",
      }),
    "新的封面候选已生成。",
  );
}

function selectDesign(design) {
  return runAction(
    `select-${design.id}`,
    () =>
      api(
        `/api/v1/red-packet/campaigns/${props.campaignId}/designs/${design.id}/select/`,
        { method: "POST", body: "{}" },
      ),
    "已选择最终封面方案。",
  );
}

function approveDesign() {
  return runAction(
    "approve",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/approve/`, {
        method: "POST",
        body: JSON.stringify({ note: "制作台完成创意确认" }),
      }),
    "封面已通过创意确认，进入权利审核。",
  );
}

function validateCampaign() {
  return runAction(
    "validate",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/validate/`, {
        method: "POST",
        body: "{}",
      }),
    "红包封面 QA 已完成。",
  );
}

function exportCampaign() {
  return runAction(
    "export",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/export/`, {
        method: "POST",
        body: "{}",
      }),
    "红包封面投稿包已生成。",
  );
}

async function uploadDesign(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const body = new FormData();
  body.append("file", file);
  await runAction(
    "upload",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/upload/`, {
        method: "POST",
        body,
      }),
    "封面已上传并规范化。",
  );
  event.target.value = "";
}

function openSubmission() {
  submission.value = latestSubmission.value
    ? {
        id: latestSubmission.value.id,
        platform_work_id: latestSubmission.value.platform_work_id || "",
        status: latestSubmission.value.status,
        rejection_reason: latestSubmission.value.rejection_reason || "",
        notes: latestSubmission.value.notes || "",
      }
    : {
        id: null,
        platform_work_id: "",
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
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/submissions/`, {
        method: isUpdate ? "PATCH" : "POST",
        body: JSON.stringify(submission.value),
      }),
    isUpdate ? "微信审核反馈已更新。" : "微信人工提交记录已保存。",
  );
  showSubmission.value = false;
}

async function createOrder() {
  await runAction(
    "order",
    () =>
      api(`/api/v1/red-packet/campaigns/${props.campaignId}/orders/`, {
        method: "POST",
        body: JSON.stringify(orderForm.value),
      }),
    "库存订单已登记。",
  );
  showOrder.value = false;
}

function openDistribution(order) {
  activeOrder.value = order;
  distributionForm.value = {
    channel: "社群发放",
    quantity: Math.min(10, order.available_quantity),
    notes: "",
  };
  showDistribution.value = true;
}

async function createDistribution() {
  await runAction(
    "distribution",
    () =>
      api(
        `/api/v1/red-packet/campaigns/${props.campaignId}/orders/${activeOrder.value.id}/distributions/`,
        {
          method: "POST",
          body: JSON.stringify(distributionForm.value),
        },
      ),
    "发放批次已登记。",
  );
  showDistribution.value = false;
}

onMounted(refresh);
</script>

<template>
  <div v-loading="loading" class="wb product-wb">
    <template v-if="campaign">
      <header class="wb-header">
        <div>
          <div class="wb-title-line">
            <h1>{{ campaign.name }}</h1>
            <el-tag effect="plain" round>{{ campaign.status_label }}</el-tag>
          </div>
          <p>
            {{ campaign.audience || "未定义受众" }} ·
            {{ campaign.designs.length }} 个方案 · 计划发放
            {{ campaign.planned_quantity }} 份
          </p>
        </div>
        <div class="wb-header-actions">
          <el-button
            :icon="Upload"
            :loading="busyAction === 'upload'"
            @click="uploadInput?.click()"
          >
            上传封面
          </el-button>
          <input
            ref="uploadInput"
            class="sr-only"
            type="file"
            accept=".png,.jpg,.jpeg,image/png,image/jpeg"
            @change="uploadDesign"
          />
          <el-button
            type="primary"
            :icon="MagicStick"
            :disabled="!['draft', 'brief_approved', 'rework'].includes(campaign.status)"
            :loading="busyAction === 'generate'"
            @click="generateDesigns"
          >
            生成候选
          </el-button>
        </div>
      </header>

      <section class="wb-flow product-flow" aria-label="红包封面生产进度">
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
              <h2>设计候选与选稿</h2>
              <p>原稿和处理后版本独立保存；重新生成不会覆盖已经确认的资产。</p>
            </div>
          </div>

          <div v-if="!campaign.designs.length" class="wb-empty">
            <MagicStick />
            <strong>从封面故事生成第一轮候选</strong>
            <p>本地案例会生成可完整走通 QA 和导出的封面素材。</p>
            <el-button type="primary" @click="generateDesigns">生成封面候选</el-button>
          </div>

          <div v-else class="cover-design-grid">
            <article
              v-for="design in campaign.designs"
              :key="design.id"
              class="cover-design"
              :class="{ 'is-selected': design.is_selected }"
            >
              <button
                class="cover-preview"
                type="button"
                :aria-pressed="design.is_selected"
                @click="selectDesign(design)"
              >
                <img :src="design.asset.url" :alt="design.title" loading="lazy" />
                <span v-if="design.is_selected" class="cover-selected">
                  <CircleCheck /> 已选
                </span>
              </button>
              <div class="cover-design-meta">
                <div>
                  <strong>{{ design.title }}</strong>
                  <span>{{ design.asset.width }}×{{ design.asset.height }} · {{ Math.ceil(design.asset.size_bytes / 1024) }}KB</span>
                </div>
                <el-tag v-if="design.is_approved" type="success" effect="light">创意通过</el-tag>
                <el-button
                  v-else
                  size="small"
                  :icon="Select"
                  @click="selectDesign(design)"
                >
                  选用
                </el-button>
              </div>
            </article>
          </div>

          <section class="product-section">
            <div class="section-header">
              <h2 class="section-title">库存与发放</h2>
              <el-button
                size="small"
                :icon="Box"
                :disabled="!['approved', 'distributing'].includes(campaign.status)"
                @click="showOrder = true"
              >
                登记下单
              </el-button>
            </div>
            <div class="table-wrap">
              <table class="data-table">
                <thead><tr><th>平台订单</th><th>总量</th><th>已发放</th><th>可用</th><th>状态</th><th></th></tr></thead>
                <tbody>
                  <tr v-for="order in campaign.orders" :key="order.id">
                    <td>{{ order.platform_order_no || "未登记" }}</td>
                    <td>{{ order.quantity }}</td>
                    <td>{{ order.distributed_quantity }}</td>
                    <td>{{ order.available_quantity }}</td>
                    <td>{{ order.status_label }}</td>
                    <td>
                      <el-button
                        size="small"
                        :disabled="order.available_quantity < 1"
                        @click="openDistribution(order)"
                      >
                        登记发放
                      </el-button>
                    </td>
                  </tr>
                  <tr v-if="!campaign.orders.length">
                    <td colspan="6"><div class="empty-state">微信审核通过后，在这里登记下单和渠道发放。</div></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </main>

        <aside class="wb-sidebar">
          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>创意与权利闸门</h2></div>
            <div class="side-summary">
              <strong>{{ selectedDesign ? selectedDesign.title : "尚未选稿" }}</strong>
              <span>{{ selectedDesign?.is_approved ? "已完成创意确认" : "选择方案后由审核人员确认" }}</span>
            </div>
            <el-button
              class="side-action"
              type="success"
              :icon="Select"
              :disabled="!selectedDesign || selectedDesign.is_approved"
              :loading="busyAction === 'approve'"
              @click="approveDesign"
            >
              确认最终封面
            </el-button>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>确定性 QA</h2></div>
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
            <p v-else class="side-empty">检查尺寸、格式、体积、封面故事、选稿和权利材料。</p>
            <ul v-if="latestValidation?.issues?.length" class="issue-list">
              <li v-for="issue in latestValidation.issues" :key="issue.id">
                <Warning />
                <div><strong>{{ issue.message }}</strong><span>{{ issue.remediation }}</span></div>
              </li>
            </ul>
            <el-button
              class="side-action"
              :loading="busyAction === 'validate'"
              @click="validateCampaign"
            >
              运行 QA
            </el-button>
          </section>

          <section class="wb-side-section">
            <div class="wb-side-heading"><h2>提交与平台反馈</h2></div>
            <a v-if="latestExport" class="export-link" :href="latestExport.download_url">
              <Download />
              <div><strong>下载红包封面投稿包</strong><span>{{ latestExport.checksum_sha256.slice(0, 12) }}…</span></div>
            </a>
            <p v-else class="side-empty">QA 通过后冻结规则快照并生成 ZIP。</p>
            <el-button
              class="side-action"
              :loading="busyAction === 'export'"
              @click="exportCampaign"
            >
              生成投稿包
            </el-button>
            <el-button
              class="side-action"
              :disabled="!latestExport"
              @click="openSubmission"
            >
              {{ latestSubmission ? "更新微信审核" : "登记人工提交" }}
            </el-button>
          </section>
        </aside>
      </div>
    </template>

    <el-dialog v-model="showSubmission" title="微信红包封面审核记录" width="min(520px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="平台作品编号"><el-input v-model="submission.platform_work_id" /></el-form-item>
        <el-form-item label="审核状态">
          <el-select v-model="submission.status" style="width: 100%">
            <el-option label="已提交" value="submitted" />
            <el-option label="审核中" value="in_review" />
            <el-option label="已驳回" value="rejected" />
            <el-option label="审核通过" value="approved" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="submission.status === 'rejected'" label="驳回原因">
          <el-input v-model="submission.rejection_reason" type="textarea" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model="submission.notes" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showSubmission = false">取消</el-button><el-button type="primary" @click="saveSubmission">保存</el-button></template>
    </el-dialog>

    <el-dialog v-model="showOrder" title="登记红包封面下单" width="min(520px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="平台订单号"><el-input v-model="orderForm.platform_order_no" /></el-form-item>
        <el-form-item label="购买数量"><el-input v-model.number="orderForm.quantity" type="number" min="1" /></el-form-item>
        <el-form-item label="单价"><el-input v-model.number="orderForm.unit_cost" type="number" min="0" step="0.01" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="orderForm.notes" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showOrder = false">取消</el-button><el-button type="primary" @click="createOrder">保存库存</el-button></template>
    </el-dialog>

    <el-dialog v-model="showDistribution" title="登记发放批次" width="min(520px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="渠道"><el-input v-model="distributionForm.channel" /></el-form-item>
        <el-form-item label="发放数量"><el-input v-model.number="distributionForm.quantity" type="number" min="1" :max="activeOrder?.available_quantity" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="distributionForm.notes" type="textarea" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="showDistribution = false">取消</el-button><el-button type="primary" @click="createDistribution">确认发放</el-button></template>
    </el-dialog>
  </div>
</template>
