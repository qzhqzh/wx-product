import { createApp } from "vue";
import {
  ElButton,
  ElDialog,
  ElForm,
  ElFormItem,
  ElInput,
  ElLoading,
  ElOption,
  ElSelect,
  ElTag,
} from "element-plus";
import "element-plus/es/components/base/style/css";
import "element-plus/es/components/button/style/css";
import "element-plus/es/components/dialog/style/css";
import "element-plus/es/components/form/style/css";
import "element-plus/es/components/form-item/style/css";
import "element-plus/es/components/input/style/css";
import "element-plus/es/components/loading/style/css";
import "element-plus/es/components/option/style/css";
import "element-plus/es/components/select/style/css";
import "element-plus/es/components/tag/style/css";
import "./workbench.css";
import MiniProgramWorkbench from "./MiniProgramWorkbench.vue";
import PackWorkbench from "./PackWorkbench.vue";
import RedPacketWorkbench from "./RedPacketWorkbench.vue";

function mountWorkbench(selector, component, props) {
  const mount = document.querySelector(selector);
  if (!mount) return;

  const app = createApp(component, props(mount));
  for (const component of [
    ElButton,
    ElDialog,
    ElForm,
    ElFormItem,
    ElInput,
    ElOption,
    ElSelect,
    ElTag,
  ]) {
    app.component(component.name, component);
  }
  app.directive("loading", ElLoading.directive);
  app.mount(mount);
}

mountWorkbench("#pack-workbench", PackWorkbench, (mount) => ({
  packId: mount.dataset.packId,
}));
mountWorkbench("#red-packet-workbench", RedPacketWorkbench, (mount) => ({
  campaignId: mount.dataset.campaignId,
}));
mountWorkbench("#mini-program-workbench", MiniProgramWorkbench, (mount) => ({
  releaseId: mount.dataset.releaseId,
}));
